# License: MIT
# Copyright © 2022 Frequenz Energy-as-a-Service GmbH

"""An actor to resample microgrid component metrics."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import AsyncIterator

from frequenz.channels import Receiver, Sender

from frequenz.sdk.util.asyncio import cancel_and_await

from ..timeseries import Sample
from ..timeseries.resampling import (
    Resampler,
    ResamplingError,
    ResamplingFunction,
    average,
)
from ._channel_registry import ChannelRegistry
from ._data_sourcing import ComponentMetricRequest
from ._decorator import actor

logger = logging.Logger(__name__)


@actor
class ComponentMetricsResamplingActor:
    """An actor to resample microgrid component metrics."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        channel_registry: ChannelRegistry,
        data_sourcing_request_sender: Sender[ComponentMetricRequest],
        resampling_request_receiver: Receiver[ComponentMetricRequest],
        resampling_period_s: float = 0.2,
        max_data_age_in_periods: float = 3.0,
        resampling_function: ResamplingFunction = average,
    ) -> None:
        """Initialize an instance.

        Args:
            channel_registry: The channel registry used to get senders and
                receivers for data sourcing subscriptions.
            data_sourcing_request_sender: The sender used to send requests to
                the [`DataSourcingActor`][frequenz.sdk.actor.DataSourcingActor]
                to subscribe to component metrics.
            resampling_request_receiver: The receiver to use to receive new
                resampmling subscription requests.
            resampling_period_s: The time it passes between resampled data
                should be calculated (in seconds).
            max_data_age_in_periods: The maximum age a sample can have to be
                considered *relevant* for resampling purposes, expressed in the
                number of resampling periods. For exapmle is
                `resampling_period_s` is 3 and `max_data_age_in_periods` is 2,
                then data older than `3*2 = 6` secods will be discarded when
                creating a new sample and never passed to the resampling
                function.
            resampling_function: The function to be applied to the sequence of
                *relevant* samples at a given time. The result of the function
                is what is sent as the resampled data.
        """
        self._channel_registry = channel_registry
        self._resampling_period_s = resampling_period_s
        self._max_data_age_in_periods: float = max_data_age_in_periods
        self._resampling_function: ResamplingFunction = resampling_function
        self._data_sourcing_request_sender = data_sourcing_request_sender
        self._resampling_request_receiver = resampling_request_receiver
        self._resampler = Resampler(
            resampling_period_s=resampling_period_s,
            max_data_age_in_periods=max_data_age_in_periods,
            resampling_function=resampling_function,
        )
        self._senders: dict[AsyncIterator[Sample], Sender[Sample]] = {}

    async def _subscribe(self, request: ComponentMetricRequest) -> None:
        """Request data for a component metric.

        Args:
            request: The request for component metric data.
        """
        data_source_request = dataclasses.replace(
            request, namespace=request.namespace + ":Source"
        )
        data_source_channel_name = data_source_request.get_channel_name()
        await self._data_sourcing_request_sender.send(data_source_request)
        receiver = self._channel_registry.new_receiver(data_source_channel_name)
        sender = self._channel_registry.new_sender(request.get_channel_name())

        self._senders[receiver] = sender
        self._resampler.add_timeseries(receiver)

    async def _process_resampling_requests(self) -> None:
        """Process resampling data requests."""
        async for request in self._resampling_request_receiver:
            await self._subscribe(request)

    async def _resample(self) -> None:
        """Do the resampling."""
        while True:
            try:
                async for samples in self._resampler.resample():
                    await asyncio.gather(
                        *[
                            self._senders[source].send(sample)
                            for source, sample in samples.items()
                        ]
                    )
            except ResamplingError as err:
                # Send whatever we got
                if err.samples:
                    await asyncio.gather(
                        *[
                            self._senders[source].send(sample)
                            for source, sample in err.samples.items()
                        ]
                    )
                # Remove failing timeseries
                for source, source_error in err.exceptions.items():
                    logger.exception(
                        "Error resampling source %s, removing source...",
                        source,
                        exc_info=source_error,
                    )
                    removed = self._resampler.remove_timeseries(source)
                    popped = self._senders.pop(source, None)
                    if not removed or not popped:
                        logger.warning(
                            "Got an exception from an unknown source: "
                            "source=%r, exception=%r resampler=%s, senders=%s",
                            source,
                            source_error,
                            removed,
                            popped,
                            exc_info=source_error,
                        )

    async def run(self) -> None:
        """Resample known component metrics and process resampling requests.

        If there is a resampling error while resampling some component metric,
        then that metric will be discarded and not resampled any more. Any
        other error will be propagated (most likely ending in the actor being
        restarted).

        Raises:
            RuntimeError: If there is some unexpected error while resampling or
                handling requests.

        # noqa: DAR401 error
        """
        tasks_to_cancel: set[asyncio.Task] = set()
        try:
            subscriptions_task = asyncio.create_task(
                self._process_resampling_requests()
            )
            tasks_to_cancel.add(subscriptions_task)

            while True:
                resampling_task = asyncio.create_task(self._resample())
                tasks_to_cancel.add(resampling_task)
                done, _ = await asyncio.wait(
                    [resampling_task, subscriptions_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if subscriptions_task in done:
                    tasks_to_cancel.remove(subscriptions_task)
                    raise RuntimeError(
                        "There was a problem with the subscriptions channel."
                    )

                if resampling_task in done:
                    tasks_to_cancel.remove(resampling_task)
                    # The resampler shouldn't end without an exception
                    error = resampling_task.exception()
                    assert (
                        error is not None
                    ), "The resample() function shouldn't exit without an exception."

                    # We don't know what to do with whatever error comes that
                    # wasn't handled in self._resample(), so propagate the
                    # exception if that is the case.
                    raise error
                    # The resampling_task will be re-created if we reached this point
        finally:
            await asyncio.gather(*[cancel_and_await(t) for t in tasks_to_cancel])

            # XXX: Here we should probably do a:  pylint: disable=fixme
            # await self._resampler.stop()
            # But since the actor will be restarted, the internal state would
            # be broken if we stop the resampler.
            #
            # We have an even bigger problem with this naive restarting
            # approach, as restarting this actor without really resetting its
            # state would be mostly the same as not really leaving the run()
            # method and just swallow any exception, which doesn't look super
            # smart.
