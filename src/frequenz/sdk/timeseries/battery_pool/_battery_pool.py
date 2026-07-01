# License: MIT
# Copyright © 2023 Frequenz Energy-as-a-Service GmbH

"""An external interface for the BatteryPool.

Allows for actors interested in operating on the same set of batteries to share
underlying formula and metric calculator instances, but without having to
specify their individual priorities with each request.
"""

import asyncio

from frequenz.quantities import Energy, Percentage, Power, Temperature
from typing_extensions import override

from ... import timeseries
from ..._internal._channels import ReceiverFetcher
from ...microgrid import _power_managing, connection_manager
from ...timeseries import Sample
from .._base_types import SystemBounds
from ..component_pool import ComponentPool
from ..formulas import Formula
from ._battery_pool_reference_store import BatteryPoolReferenceStore
from ._methods import SendOnUpdate
from ._metric_calculator import (
    CapacityCalculator,
    PowerBoundsCalculator,
    SoCCalculator,
    TemperatureCalculator,
)
from .messages import BatteryPoolReport

# pylint: disable=protected-access


class BatteryPool(ComponentPool[BatteryPoolReferenceStore, BatteryPoolReport]):
    """An interface for interaction with pools of batteries.

    Provides:
      - properties for fetching reporting streams of instantaneous
        [`power`][.power],
        [`soc`][.soc],
        [`capacity`][.capacity] values and
        available power bounds and other status through
        [`power_status`][.power_status].
      - control methods for proposing power values, namely:
        [`propose_power`][.propose_power],
        [`propose_charge`][.propose_charge] and
        [`propose_discharge`][.propose_discharge].
    """

    async def propose_charge(self, power: Power | None) -> None:
        """Set the given charge power for the batteries in the pool.

        Power values need to be positive values, indicating charge power.

        When using the Passive Sign Convention, the
        [`propose_power`][..propose_power]
        method might be more convenient.

        If the same batteries are shared by multiple actors, the behaviour is the same
        as that of the [`propose_power`][..propose_power] method, when calling it with
        `None` bounds.  The bounds for lower priority actors can't be specified with
        this method.  If that's required, use the [`propose_power`][..propose_power]
        method instead.

        Args:
            power: The unsigned charge power to propose for the batteries in the pool.
                If None, the proposed power of higher priority actors will take
                precedence as the target power.

        Raises:
            ValueError: If the given power is negative.
        """
        if power and power < Power.zero():
            raise ValueError("Charge power must be positive.")
        await self._pool_ref_store.power_manager_requests_sender.send(
            _power_managing.Proposal(
                source_id=self._source_id,
                preferred_power=power,
                bounds=timeseries.Bounds(None, None),
                component_ids=self._pool_ref_store.component_ids,
                priority=self._priority,
                creation_time=asyncio.get_running_loop().time(),
            )
        )

    async def propose_discharge(self, power: Power | None) -> None:
        """Set the given discharge power for the batteries in the pool.

        Power values need to be positive values, indicating discharge power.

        When using the Passive Sign Convention, the
        [`propose_power`][..propose_power]
        method might be more convenient.

        If the same batteries are shared by multiple actors, the behaviour is the same
        as that of the [`propose_power`][..propose_power] method, when calling it with
        `None` bounds.  The bounds for lower priority actors can't be specified with
        this method.  If that's required, use the [`propose_power`][..propose_power]
        method instead.

        Args:
            power: The unsigned discharge power to propose for the batteries in the
                pool.  If None, the proposed power of higher priority actors will take
                precedence as the target power.

        Raises:
            ValueError: If the given power is negative.
        """
        if power:
            if power < Power.zero():
                raise ValueError("Discharge power must be positive.")
            power = -power
        await self._pool_ref_store.power_manager_requests_sender.send(
            _power_managing.Proposal(
                source_id=self._source_id,
                preferred_power=power,
                bounds=timeseries.Bounds(None, None),
                component_ids=self._pool_ref_store.component_ids,
                priority=self._priority,
                creation_time=asyncio.get_running_loop().time(),
            )
        )

    @property
    @override
    def power(self) -> Formula[Power]:
        """The total power of the batteries in the pool.

        This formula produces values that are in the Passive Sign Convention (PSC).

        If a formula to calculate this metric is not already running, it will be
        started.

        A receiver from the formula can be obtained by calling the `new_receiver`
        method.
        """
        return self._pool_ref_store.formula_pool.from_power_formula(
            "battery_pool_power",
            connection_manager.get().component_graph.battery_formula(
                self._pool_ref_store.component_ids
            ),
        )

    @property
    def soc(self) -> ReceiverFetcher[Sample[Percentage]]:
        """The normalized average weighted-by-capacity SoC values for the pool.

        The SoC values are normalized to the 0-100% range and clamped if they are out
        of bounds. Only values from working batteries with operational inverters are
        considered in the calculation.

        Average SoC is calculated using the formula:
        ```
        working_batteries: Set[BatteryData] # working batteries from the battery pool

        soc_scaled = min(max(
            0,
            (soc - soc_lower_bound) / (soc_upper_bound - soc_lower_bound) * 100,
        ), 100)
        used_capacity = sum(
            battery.usable_capacity * battery.soc_scaled
            for battery in working_batteries
        )
        total_capacity = sum(battery.usable_capacity for battery in working_batteries)
        average_soc = used_capacity/total_capacity
        ```

        `None` values will be sent if there are no working batteries with operational
        inverters to calculate the metric with.

        A receiver from the MetricAggregator can be obtained by calling the
        `new_receiver` method.
        """
        assert isinstance(self._pool_ref_store, BatteryPoolReferenceStore)

        method_name = SendOnUpdate.name() + "_" + SoCCalculator.name()

        if method_name not in self._pool_ref_store._active_methods:
            calculator = SoCCalculator(self._pool_ref_store.component_ids)
            self._pool_ref_store._active_methods[method_name] = SendOnUpdate(
                metric_calculator=calculator,
                working_batteries=self._pool_ref_store._working_batteries,
                min_update_interval=self._pool_ref_store._min_update_interval,
            )

        return self._pool_ref_store._active_methods[method_name]

    @property
    def temperature(self) -> ReceiverFetcher[Sample[Temperature]]:
        """The average temperature of the batteries in the pool."""
        assert isinstance(self._pool_ref_store, BatteryPoolReferenceStore)

        method_name = SendOnUpdate.name() + "_" + TemperatureCalculator.name()

        if method_name not in self._pool_ref_store._active_methods:
            calculator = TemperatureCalculator(self._pool_ref_store.component_ids)
            self._pool_ref_store._active_methods[method_name] = SendOnUpdate(
                metric_calculator=calculator,
                working_batteries=self._pool_ref_store._working_batteries,
                min_update_interval=self._pool_ref_store._min_update_interval,
            )
        return self._pool_ref_store._active_methods[method_name]

    @property
    def capacity(self) -> ReceiverFetcher[Sample[Energy]]:
        """The capacity of the batteries in the pool.

        The reported capacity values consider only working batteries with operational
        inverters.

        Calculated with the formula:
        ```
        working_batteries: Set[BatteryData] # working batteries from the battery pool
        total_capacity = sum(
            battery.capacity * (soc_upper_bound - soc_lower_bound) / 100
            for battery in working_batteries
        )
        ```

        `None` will be sent if there are no working batteries with operational
        inverters to calculate metrics.

        A receiver from the MetricAggregator can be obtained by calling the
        `new_receiver` method.
        """
        assert isinstance(self._pool_ref_store, BatteryPoolReferenceStore)

        method_name = SendOnUpdate.name() + "_" + CapacityCalculator.name()

        if method_name not in self._pool_ref_store._active_methods:
            calculator = CapacityCalculator(self._pool_ref_store.component_ids)
            self._pool_ref_store._active_methods[method_name] = SendOnUpdate(
                metric_calculator=calculator,
                working_batteries=self._pool_ref_store._working_batteries,
                min_update_interval=self._pool_ref_store._min_update_interval,
            )

        return self._pool_ref_store._active_methods[method_name]

    @override
    @property
    def system_power_bounds(self) -> ReceiverFetcher[SystemBounds]:
        """The power bounds of the batteries in the pool.

        Power bounds refer to the min and max power that a battery can
        discharge or charge at and is also denoted as SoP.

        Power bounds formulas are described in the receiver return type.
        None will be sent if there is no component to calculate metrics.

        A receiver from the MetricAggregator can be obtained by calling the
        `new_receiver` method.
        """
        assert isinstance(self._pool_ref_store, BatteryPoolReferenceStore)

        method_name = SendOnUpdate.name() + "_" + PowerBoundsCalculator.name()

        if method_name not in self._pool_ref_store._active_methods:
            calculator = PowerBoundsCalculator(self._pool_ref_store.component_ids)
            self._pool_ref_store._active_methods[method_name] = SendOnUpdate(
                metric_calculator=calculator,
                working_batteries=self._pool_ref_store._working_batteries,
                min_update_interval=self._pool_ref_store._min_update_interval,
            )

        return self._pool_ref_store._active_methods[method_name]
