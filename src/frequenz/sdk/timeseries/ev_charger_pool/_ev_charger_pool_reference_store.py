# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Manages shared state/tasks for a set of EV chargers."""

import uuid
from typing import Type

from frequenz.client.microgrid.component import Component, EvCharger
from typing_extensions import override

from ..component_pool._component_pool_reference_store import ComponentPoolReferenceStore
from ._system_bounds_tracker import EVCSystemBoundsTracker


class EVChargerPoolReferenceStore(ComponentPoolReferenceStore):
    """A class for maintaining the shared state/tasks for a pool of EV chargers.

    This includes ownership of
    - the formula pool and metric calculators.
    - the tasks for calculating system bounds for the EV chargers.

    These are independent of the priority of the actors and can be shared between
    multiple users of the same set of EV chargers.

    They are exposed through the EVChargerPool class.
    """

    @staticmethod
    def get_component_class() -> Type[Component]:
        """Return the class of the component type."""
        return EvCharger

    @staticmethod
    def get_pool_type_name() -> str:
        """Return the name of the pool type, for display purposes."""
        return "EVChargerPool"

    @staticmethod
    def get_component_type_name_plural() -> str:
        """Return the name of the component type, for display purposes."""
        return "EV chargers"

    @override
    def get_namespace(self) -> str:
        """Return the namespace to use with the data pipeline."""
        return f"ev-charger-pool-{uuid.uuid4()}"

    @override
    def create_bounds_tracker(self) -> None:
        """Create the bounds tracker for the pool."""
        self.bounds_tracker = EVCSystemBoundsTracker(
            self.component_ids,
            self.status_receiver,
            self.bounds_channel.new_sender(),
        )
        self.bounds_tracker.start()
