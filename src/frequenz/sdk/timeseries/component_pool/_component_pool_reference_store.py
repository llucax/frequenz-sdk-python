# License: MIT
# Copyright © 2023 Frequenz Energy-as-a-Service GmbH

"""Abstract base class for pool reference stores."""

import asyncio
from abc import ABC, abstractmethod
from collections import abc
from typing import Type

from frequenz.channels import Broadcast, Receiver, Sender
from frequenz.client.common.microgrid.components import ComponentId
from frequenz.client.microgrid.component import Component

from frequenz.sdk._internal._channels import ChannelRegistry, ReceiverFetcher
from frequenz.sdk.actor import BackgroundService
from frequenz.sdk.microgrid import connection_manager
from frequenz.sdk.microgrid._data_sourcing import ComponentMetricRequest
from frequenz.sdk.microgrid._power_distributing import ComponentPoolStatus, Result
from frequenz.sdk.microgrid._power_managing import Proposal, ReportRequest
from frequenz.sdk.timeseries._base_types import SystemBounds
from frequenz.sdk.timeseries.formulas._formula_pool import FormulaPool


class ComponentPoolReferenceStore(ABC):
    """An abstract base class for pool reference stores."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        channel_registry: ChannelRegistry,
        resampler_subscription_sender: Sender[ComponentMetricRequest],
        status_receiver: Receiver[ComponentPoolStatus],
        power_manager_requests_sender: Sender[Proposal],
        power_manager_bounds_subs_sender: Sender[ReportRequest],
        power_distribution_results_fetcher: ReceiverFetcher[Result],
        component_ids: abc.Set[ComponentId] | None = None,
    ):
        """Initialize this instance.

        Args:
            channel_registry: A channel registry instance shared with the resampling
                actor.
            resampler_subscription_sender: A sender for sending metric requests to the
                resampling actor.
            status_receiver: A receiver that streams the status of the components in
                the pool.
            power_manager_requests_sender: A Channel sender for sending power
                requests to the power managing actor.
            power_manager_bounds_subs_sender: A Channel sender for sending power bounds
                subscription requests to the power managing actor.
            power_distribution_results_fetcher: A ReceiverFetcher for the results from
                the power distributing actor.
            component_ids: An optional list of component_ids belonging to this pool.  If
                not specified, IDs of all components of the components type of this pool
                in the microgrid will be fetched from the component graph.

        Raises:
            ValueError: If any of the provided component_ids are not of correct type or
                are unknown to the component graph.
        """
        self.channel_registry = channel_registry
        """The channel registry shared with the resampling actor."""

        self.resampler_subscription_sender = resampler_subscription_sender
        """The sender for sending metric requests to the resampling actor."""

        self.status_receiver = status_receiver
        """The receiver that streams the status of the components in the pool."""

        self.power_manager_requests_sender = power_manager_requests_sender
        """The sender for sending power requests to the power managing actor."""

        self.power_manager_bounds_subs_sender = power_manager_bounds_subs_sender
        """The sender for sending power bounds subscription requests to the power managing actor."""

        self.power_distribution_results_fetcher = power_distribution_results_fetcher
        """The fetcher for the results from the power distributing actor."""

        graph = connection_manager.get().component_graph
        all_components = frozenset(
            {
                inv.id
                for inv in graph.components(matching_types=self.get_component_class())
            }
        )

        if component_ids is not None:
            self.component_ids: frozenset[ComponentId] = frozenset(component_ids)
            """The IDs of the components belonging to this pool."""
            if not self.component_ids.issubset(all_components):
                unknown_ids = self.component_ids - all_components
                raise ValueError(
                    f"Unable to create {self.get_pool_type_name()}. These component IDs "
                    + f"are either not {self.get_component_type_name_plural()} or are unknown: "
                    + f"{unknown_ids}"
                )
        else:
            self.component_ids = all_components

        self.power_bounds_subs: dict[str, asyncio.Task[None]] = {}
        """The running power bounds subscription tasks, keyed by their identifier."""

        self.namespace = self.get_namespace()
        """The namespace to use with the data pipeline."""

        self.formula_pool = FormulaPool(
            self.namespace,
            self.channel_registry,
            self.resampler_subscription_sender,
        )
        """The formula pool for this component pool."""

        self.bounds_channel: Broadcast[SystemBounds] = Broadcast(
            name=f"System Bounds for {self.get_component_type_name_plural()}: {self.component_ids}",
            resend_latest=True,
        )
        """The channel for broadcasting the system bounds of the pool."""

        self.bounds_tracker: BackgroundService | None = None
        """The background service that tracks the system bounds of the pool."""
        self.create_bounds_tracker()

    @staticmethod
    @abstractmethod
    def get_component_class() -> Type[Component]:
        """Return the class of the component type."""

    @staticmethod
    @abstractmethod
    def get_pool_type_name() -> str:
        """Return the name of the pool type, for display purposes."""

    @staticmethod
    @abstractmethod
    def get_component_type_name_plural() -> str:
        """Return the name of the component type, for display purposes."""

    @abstractmethod
    def get_namespace(self) -> str:
        """Return the namespace to use with the data pipeline."""

    @abstractmethod
    def create_bounds_tracker(self) -> None:
        """Create the bounds tracker for the pool."""

    async def stop(self) -> None:
        """Stop all tasks and channels."""
        await self.formula_pool.stop()
        if self.bounds_tracker is not None:
            await self.bounds_tracker.stop()
        self.status_receiver.close()
