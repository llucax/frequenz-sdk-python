# License: MIT
# Copyright © 2022 Frequenz Energy-as-a-Service GmbH

"""Component data types for data coming from a microgrid."""

from abc import ABC
from collections.abc import Set
from dataclasses import dataclass
from datetime import datetime

from frequenz.client.microgrid import ComponentId
from frequenz.client.microgrid.component import ComponentErrorCode, ComponentStateCode


@dataclass(frozen=True)
class ComponentData(ABC):
    """A private base class for strongly typed component data classes."""

    component_id: ComponentId
    """The ID identifying this component in the microgrid."""

    timestamp: datetime
    """The timestamp of when the data was measured."""

    states: Set[ComponentStateCode]
    """The states of the component."""

    warnings: Set[ComponentErrorCode]
    """The warnings of the component."""

    errors: Set[ComponentErrorCode]
    """The errors of the component."""


@dataclass(frozen=True)
class MeterData(ComponentData):
    """A wrapper class for holding meter data."""

    active_power: float
    """The total active 3-phase AC power, in Watts (W).

    Represented in the passive sign convention.

    * Positive means consumption from the grid.
    * Negative means supply into the grid.
    """

    active_power_per_phase: tuple[float, float, float]
    """The per-phase AC active power for phase 1, 2, and 3 respectively, in Watt (W).

    Represented in the passive sign convention.

    * Positive means consumption from the grid.
    * Negative means supply into the grid.
    """

    reactive_power: float
    """The total reactive 3-phase AC power, in Volt-Ampere Reactive (VAr).

    * Positive power means capacitive (current leading w.r.t. voltage).
    * Negative power means inductive (current lagging w.r.t. voltage).
    """

    reactive_power_per_phase: tuple[float, float, float]
    """The per-phase AC reactive power, in Volt-Ampere Reactive (VAr).

    The provided values are for phase 1, 2, and 3 respectively.

    * Positive power means capacitive (current leading w.r.t. voltage).
    * Negative power means inductive (current lagging w.r.t. voltage).
    """

    current_per_phase: tuple[float, float, float]
    """AC current in Amperes (A) for phase/line 1,2 and 3 respectively.

    Represented in the passive sign convention.

    * Positive means consumption from the grid.
    * Negative means supply into the grid.
    """

    voltage_per_phase: tuple[float, float, float]
    """The ac voltage in volts (v) between the line and the neutral wire for phase/line
        1,2 and 3 respectively.
    """

    frequency: float
    """The AC power frequency in Hertz (Hz)."""


@dataclass(frozen=True)
class BatteryData(ComponentData):  # pylint: disable=too-many-instance-attributes
    """A wrapper class for holding battery data."""

    soc: float
    """Battery's overall SoC in percent (%)."""

    soc_lower_bound: float
    """The SoC below which discharge commands will be blocked by the system,
        in percent (%).
    """

    soc_upper_bound: float
    """The SoC above which charge commands will be blocked by the system,
        in percent (%).
    """

    capacity: float
    """The capacity of the battery in Wh (Watt-hour)."""

    power_inclusion_lower_bound: float
    """Lower inclusion bound for battery power in watts.

    This is the lower limit of the range within which power requests are allowed for the
    battery.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    power_exclusion_lower_bound: float
    """Lower exclusion bound for battery power in watts.

    This is the lower limit of the range within which power requests are not allowed for
    the battery.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    power_inclusion_upper_bound: float
    """Upper inclusion bound for battery power in watts.

    This is the upper limit of the range within which power requests are allowed for the
    battery.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    power_exclusion_upper_bound: float
    """Upper exclusion bound for battery power in watts.

    This is the upper limit of the range within which power requests are not allowed for
    the battery.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    temperature: float
    """The (average) temperature reported by the battery, in Celsius (°C)."""


@dataclass(frozen=True)
class InverterData(ComponentData):  # pylint: disable=too-many-instance-attributes
    """A wrapper class for holding inverter data."""

    active_power: float
    """The total active 3-phase AC power, in Watts (W).

    Represented in the passive sign convention.

    * Positive means consumption from the grid.
    * Negative means supply into the grid.
    """

    active_power_per_phase: tuple[float, float, float]
    """The per-phase AC active power for phase 1, 2, and 3 respectively, in Watt (W).

    Represented in the passive sign convention.

    * Positive means consumption from the grid.
    * Negative means supply into the grid.
    """

    reactive_power: float
    """The total reactive 3-phase AC power, in Volt-Ampere Reactive (VAr).

    * Positive power means capacitive (current leading w.r.t. voltage).
    * Negative power means inductive (current lagging w.r.t. voltage).
    """

    reactive_power_per_phase: tuple[float, float, float]
    """The per-phase AC reactive power, in Volt-Ampere Reactive (VAr).

    The provided values are for phase 1, 2, and 3 respectively.

    * Positive power means capacitive (current leading w.r.t. voltage).
    * Negative power means inductive (current lagging w.r.t. voltage).
    """

    current_per_phase: tuple[float, float, float]
    """AC current in Amperes (A) for phase/line 1, 2 and 3 respectively.

    Represented in the passive sign convention.

    * Positive means consumption from the grid.
    * Negative means supply into the grid.
    """

    voltage_per_phase: tuple[float, float, float]
    """The AC voltage in Volts (V) between the line and the neutral wire for
       phase/line 1, 2 and 3 respectively.
    """

    active_power_inclusion_lower_bound: float
    """Lower inclusion bound for inverter power in watts.

    This is the lower limit of the range within which power requests are allowed for the
    inverter.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    active_power_exclusion_lower_bound: float
    """Lower exclusion bound for inverter power in watts.

    This is the lower limit of the range within which power requests are not allowed for
    the inverter.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    active_power_inclusion_upper_bound: float
    """Upper inclusion bound for inverter power in watts.

    This is the upper limit of the range within which power requests are allowed for the
    inverter.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    active_power_exclusion_upper_bound: float
    """Upper exclusion bound for inverter power in watts.

    This is the upper limit of the range within which power requests are not allowed for
    the inverter.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    frequency: float
    """AC frequency, in Hertz (Hz)."""


@dataclass(frozen=True)
class EVChargerData(ComponentData):  # pylint: disable=too-many-instance-attributes
    """A wrapper class for holding ev_charger data."""

    active_power: float
    """The total active 3-phase AC power, in Watts (W).

    Represented in the passive sign convention.

    * Positive means consumption from the grid.
    * Negative means supply into the grid.
    """

    active_power_per_phase: tuple[float, float, float]
    """The per-phase AC active power for phase 1, 2, and 3 respectively, in Watt (W).

    Represented in the passive sign convention.

    * Positive means consumption from the grid.
    * Negative means supply into the grid.
    """

    current_per_phase: tuple[float, float, float]
    """AC current in Amperes (A) for phase/line 1,2 and 3 respectively.

    Represented in the passive sign convention.

    * Positive means consumption from the grid.
    * Negative means supply into the grid.
    """

    reactive_power: float
    """The total reactive 3-phase AC power, in Volt-Ampere Reactive (VAr).

    * Positive power means capacitive (current leading w.r.t. voltage).
    * Negative power means inductive (current lagging w.r.t. voltage).
    """

    reactive_power_per_phase: tuple[float, float, float]
    """The per-phase AC reactive power, in Volt-Ampere Reactive (VAr).

    The provided values are for phase 1, 2, and 3 respectively.

    * Positive power means capacitive (current leading w.r.t. voltage).
    * Negative power means inductive (current lagging w.r.t. voltage).
    """

    voltage_per_phase: tuple[float, float, float]
    """The AC voltage in Volts (V) between the line and the neutral
        wire for phase/line 1,2 and 3 respectively.
    """

    active_power_inclusion_lower_bound: float
    """Lower inclusion bound for EV charger power in watts.

    This is the lower limit of the range within which power requests are allowed for the
    EV charger.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    active_power_exclusion_lower_bound: float
    """Lower exclusion bound for EV charger power in watts.

    This is the lower limit of the range within which power requests are not allowed for
    the EV charger.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    active_power_inclusion_upper_bound: float
    """Upper inclusion bound for EV charger power in watts.

    This is the upper limit of the range within which power requests are allowed for the
    EV charger.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    active_power_exclusion_upper_bound: float
    """Upper exclusion bound for EV charger power in watts.

    This is the upper limit of the range within which power requests are not allowed for
    the EV charger.

    See [`frequenz.api.common.metrics_pb2.Metric.system_inclusion_bounds`][] and
    [`frequenz.api.common.metrics_pb2.Metric.system_exclusion_bounds`][] for more
    details.
    """

    frequency: float
    """AC frequency, in Hertz (Hz)."""

    def is_ev_connected(self) -> bool:
        """Check whether an EV is connected to the charger.

        Returns:
            When the charger is not in an error state, whether an EV is connected to
                the charger.
        """
        # Old code:
        # return self.component_state not in (
        #     EVChargerComponentState.AUTHORIZATION_REJECTED,
        #     EVChargerComponentState.ERROR,
        # ) and self.cable_state in (
        #     EVChargerCableState.EV_LOCKED,
        #     EVChargerCableState.EV_PLUGGED,
        # )
        # TODO: Verify this logic is correct

        return (
            ComponentStateCode.ERROR not in self.states
            and (
                ComponentErrorCode.UNAUTHORIZED not in self.errors
                and ComponentErrorCode.UNAUTHORIZED not in self.warnings
            )
            and bool(
                {
                    ComponentStateCode.EV_CHARGING_CABLE_LOCKED_AT_EV,
                    ComponentStateCode.EV_CHARGING_CABLE_LOCKED_AT_STATION,
                }
                & self.states
                or {
                    ComponentStateCode.EV_CHARGING_CABLE_PLUGGED_AT_EV,
                    ComponentStateCode.EV_CHARGING_CABLE_PLUGGED_AT_STATION,
                }
                & self.states
            )
        )
