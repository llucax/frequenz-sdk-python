# License: MIT
# Copyright © 2022 Frequenz Energy-as-a-Service GmbH

"""The Microgrid API data source for the DataSourcingActor."""

import asyncio
import logging
from typing import NamedTuple

from frequenz.channels import Receiver, Sender, merge, select, selected_from
from frequenz.channels.event import Event
from frequenz.client.microgrid import ComponentId
from frequenz.client.microgrid.component import ComponentDataSamples
from frequenz.client.microgrid.metrics import Metric
from frequenz.quantities import Quantity

from ..._internal._asyncio import run_forever
from ..._internal._channels import ChannelRegistry
from ...microgrid import connection_manager
from ...timeseries import Sample
from ._component_metric_request import ComponentMetricRequest

_logger = logging.getLogger(__name__)


class _ComponentMetricKey(NamedTuple):
    component_id: ComponentId
    metric: Metric | int


class _ComponentMetricStream(NamedTuple):
    """A stream of component data samples and senders for a component metric.

    Each metric we subscribe to will have a corresponding stream of incoming data
    samples, but given that we might have different requestors for the same metric,
    we might have multiple senders for the same metric.
    """

    receiver: Receiver[ComponentDataSamples]
    """The receiver to receive the data samples from the API."""

    senders: dict[str, Sender[Sample[Quantity]]]
    """The senders send the received data samples, identified by the channel's name."""


class MicrogridApiSource:
    """Fetches requested metrics from the Microgrid API.

    Used by the DataSourcingActor.
    """

    def __init__(
        self,
        registry: ChannelRegistry,
    ) -> None:
        """Create a `MicrogridApiSource` instance.

        Args:
            registry: A channel registry.  To be replaced by a singleton
                instance.
        """
        self._registry = registry
        self._streams: dict[_ComponentMetricKey, _ComponentMetricStream] = {}
        self._refresh_streams_event: Event = Event(
            name="MicrogridApiSource._refresh_streams"
        )
        self._run_task: asyncio.Task[None] = asyncio.create_task(
            run_forever(self._run), name="MicrogridApiSource._run"
        )

    async def _run(self) -> None:
        """Run the Microgrid API source."""
        metric_receivers = [s.receiver for s in self._streams.values()]
        async for selected in select(
            self._refresh_streams_event, merge(*metric_receivers)
        ):
            if selected_from(selected, self._refresh_streams_event):
                _ = selected.message  # ACK
                _logger.debug("Refreshing streams")
                # Breaking will just restart the select loop, as this runs using
                # run_forever
                break
            if selected_from(selected, *metric_receivers):
                await self._handle_incoming_samples(selected.message)
            else:
                assert False, "Unexpected selected channel"

    async def _handle_incoming_samples(self, samples: ComponentDataSamples) -> None:
        """Handle incoming samples from the API.

        For each metric sample, send the sample to the corresponding output channels.

        Args:
            samples: The incoming component data samples.
        """
        for metric_sample in samples.metrics:
            key = _ComponentMetricKey(samples.component_id, metric_sample.metric)
            raw_value = metric_sample.as_single_value()
            value = Quantity(raw_value) if raw_value is not None else None
            sample = Sample(metric_sample.sampled_at, value)
            senders = self._streams[key].senders

            results = await asyncio.gather(
                *[sender.send(sample) for sender in senders.values()],
                return_exceptions=True,
            )

            errors = [
                (error, channel_name)
                for error, channel_name in zip(results, senders)
                if error is not None
            ]
            for error, channel_name in errors:
                _logger.exception(
                    "Error while sending sample %s for component %s to channel %s: %s",
                    sample,
                    samples.component_id,
                    channel_name,
                    error,
                    exc_info=error,
                )

    def _create_sender(self, channel_name: str) -> Sender[Sample[Quantity]]:
        """Create a sender for a channel."""
        return self._registry.get_or_create(Sample[Quantity], channel_name).new_sender()

    async def add_metric(self, request: ComponentMetricRequest) -> None:
        """Add a metric to be streamed from the microgrid API.

        Args:
            request: A request object for a metric, received from a downstream
                actor.
        """
        key = _ComponentMetricKey(request.component_id, request.metric)
        channel_name = request.get_channel_name()

        # If we are already subscribed to this metric and component, just add the
        # new channel to the senders
        if stream := self._streams.get(key):
            # Unless we received the same request before, in that case we do nothing
            if channel_name in stream.senders:
                return

            stream.senders[channel_name] = self._create_sender(channel_name)
            return

        # If we are not subscribed to this metric and component, subscribe to it, create
        # a stream, and add the new channel to the senders and notify the run loop
        # to refresh the streams
        api_client = connection_manager.get().api_client
        receiver = await api_client.receive_component_data_samples_stream(
            request.component_id, [request.metric]
        )
        stream = _ComponentMetricStream(
            receiver=receiver, senders={channel_name: self._create_sender(channel_name)}
        )
        self._streams[key] = stream
        self._refresh_streams_event.set()
