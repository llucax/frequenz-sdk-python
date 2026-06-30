# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Power distribution state tracking for EV chargers."""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from frequenz.client.common.microgrid.components import ComponentId
from frequenz.quantities import Power

from ...._old_component_data import EVChargerData


@dataclass
class EvcState:
    """A class for tracking the state of an EV charger."""

    component_id: ComponentId
    """The component ID of the EV charger."""

    last_data: EVChargerData
    """The last data received from the EV charger."""

    power: Power
    """The power currently used by the EV charger."""

    last_allocation: Power
    """The last allocation made for the EV."""

    last_reallocation_time: datetime
    """The last time the EV charger was allocated power.

    Used to make sure we don't allocate power to the EV charger too often.
    """

    last_charging_time: datetime
    """The last time the EV charger was charging.

    Used to de-allocate power from the EV charger if it has not been charging
    for a while.
    """

    def update_last_allocation(self, allocation: Power, alloc_time: datetime) -> None:
        """Update the last allocation and related timestamps.

        Args:
            allocation: The most recent allocation made for the EV.
            alloc_time: The time at which the allocation was made.
        """
        self.last_allocation = allocation
        self.last_reallocation_time = alloc_time
        self.last_charging_time = alloc_time

    def update_state(
        self,
        latest_ev_data: EVChargerData,
    ) -> None:
        """Update EvcState from component data.

        Args:
            latest_ev_data: Latest EV data from component data stream.
        """
        self.power = Power.from_watts(latest_ev_data.active_power)
        self.last_data = latest_ev_data

        if self.power > Power.zero():
            self.last_charging_time = latest_ev_data.timestamp


class EvcStates:
    """A tracker for the states of all EV chargers."""

    _states: dict[ComponentId, EvcState]

    def __init__(self) -> None:
        """Initialize this instance."""
        self._states = {}

    def get_ev_total_used_power(self) -> Power:
        """Return the total power consumed by all EV Chargers."""
        total_used = Power.zero()
        for evc in self._states.values():
            total_used += evc.power
        return total_used

    def get_total_allocated_power(self) -> Power:
        """Return the total power allocated to all EV Chargers."""
        total_allocated = Power.zero()
        for evc in self._states.values():
            total_allocated += evc.last_allocation
        return total_allocated

    def get(self, component_id: ComponentId) -> EvcState:
        """Return a reference to the EvcState object with the given component_id.

        Args:
            component_id: Identifies the object to retrieve.

        Returns:
            The EvcState object with the given component_id.
        """
        return self._states[component_id]

    def add_evc(self, state: EvcState) -> None:
        """Add the given EvcState object to the list.

        Args:
            state: The EvcState object to add to the list.
        """
        self._states[state.component_id] = state

    def values(self) -> Iterable[EvcState]:
        """Return an iterator over all EvcState objects.

        Returns:
            An iterator over all EvcState objects.
        """
        return self._states.values()

    def __contains__(self, component_id: ComponentId) -> bool:
        """Return whether the given component_id has an associated EvcState object.

        Args:
            component_id: The component ID to test.

        Returns:
            Whether the given component_id is a known EvCharger.
        """
        return component_id in self._states
