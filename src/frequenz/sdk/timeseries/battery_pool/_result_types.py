# License: MIT
# Copyright © 2023 Frequenz Energy-as-a-Service GmbH

"""Methods for processing battery-inverter data."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Bound:
    """Lower and upper bound values."""

    lower: float
    """Lower bound."""

    upper: float
    """Upper bound."""


@dataclass
class CapacityMetrics:
    """Capacity metrics."""

    # compare = False tells the dataclass to not use name for comparison methods
    timestamp: datetime = field(compare=False)
    """Timestamp of the metrics,"""

    total_capacity: float
    """Total batteries capacity.

    Calculated with the formula:
    ```python
    working_batteries: Set[BatteryData] # working batteries from the battery pool
    total_capacity = sum(battery.capacity for battery in working_batteries)
    ```
    """
    bound: Bound
    """Capacity bounds.

    Bounds are calculated with the formula:
    ```python
    working_batteries: Set[BatteryData] # working batteries from the battery
    bound.lower = sum(
        battery.capacity * battery.soc_lower_bound for battery in working_batteries)

    bound.upper = sum(
        battery.capacity * battery.soc_upper_bound for battery in working_batteries)
    ```
    """


@dataclass
class SoCMetrics:
    """Soc metrics."""

    # compare = False tells the dataclass to not use name for comparison methods
    timestamp: datetime = field(compare=False)
    """Timestamp of the metrics."""

    average_soc: float
    """Average SoC of working batteries in the pool, weighted by usable capacity.

    The values are normalized to the 0-100% range.

    Average soc is calculated with the formula:
    ```python
    working_batteries: Set[BatteryData] # working batteries from the battery pool

    battery.soc_scaled = max(
        0,
        (soc - soc_lower_bound) / (soc_upper_bound - soc_lower_bound) * 100,
    )
    used_capacity = sum(
        battery.usable_capacity * battery.soc_scaled
        for battery in working_batteries
    )
    total_capacity = sum(battery.usable_capacity for battery in working_batteries)
    average_soc = used_capacity/total_capacity
    ```
    """


@dataclass
class PowerMetrics:
    """Power bounds metrics."""

    # compare = False tells the dataclass to not use name for comparison methods
    timestamp: datetime = field(compare=False)
    """Timestamp of the metrics."""

    supply_bound: Bound
    """Supply power bounds.

    Upper bound is always 0 and will be supported later.
    Lower bound is negative number calculated with with the formula:
    ```python
    working_pairs: Set[BatteryData, InverterData] # working batteries from the battery
        pool and adjacent inverters

    supply_bound.lower = sum(
        max(
            battery.power_lower_bound, inverter.active_power_lower_bound)
            for each working battery in battery pool
            )
        )
    ```
    """

    consume_bound: Bound
    """Consume power bounds.

    Lower bound is always 0 and will be supported later.
    Upper bound is positive number calculated with with the formula:
    ```python
    working_pairs: Set[BatteryData, InverterData] # working batteries from the battery
        pool and adjacent inverters

    consume_bound.upper = sum(
        min(
            battery.power_upper_bound, inverter.active_power_upper_bound)
            for each working battery in battery pool
            )
        )
    ```
    """
