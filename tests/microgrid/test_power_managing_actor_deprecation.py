# License: MIT
# Copyright © 2025 Frequenz Energy-as-a-Service GmbH

"""Tests for PowerManagingActor deprecated parameter handling."""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from frequenz.channels import Broadcast
from frequenz.client.microgrid.component import (
    Battery,
    ComponentCategory,
    EvCharger,
    InverterType,
    SolarInverter,
)

from frequenz.sdk._internal._channels import ChannelRegistry
from frequenz.sdk.microgrid._power_managing._base_classes import (
    Algorithm,
    DefaultPower,
    Proposal,
    ReportRequest,
)
from frequenz.sdk.microgrid._power_managing._power_managing_actor import (
    PowerManagingActor,
    _convert_legacy_params_to_component_class,
)


class TestLegacyParamsConversion:
    """Test the legacy parameter conversion helper function."""

    def test_convert_battery(self) -> None:
        """Test conversion of BATTERY category."""
        result = _convert_legacy_params_to_component_class(
            ComponentCategory.BATTERY, None
        )
        assert result == Battery

    def test_convert_ev_charger(self) -> None:
        """Test conversion of EV_CHARGER category."""
        result = _convert_legacy_params_to_component_class(
            ComponentCategory.EV_CHARGER, None
        )
        assert result == EvCharger

    def test_convert_solar_inverter(self) -> None:
        """Test conversion of INVERTER + SOLAR category/type."""
        result = _convert_legacy_params_to_component_class(
            ComponentCategory.INVERTER, InverterType.SOLAR
        )
        assert result == SolarInverter

    def test_unsupported_inverter_type(self) -> None:
        """Test that unsupported inverter types raise ValueError."""
        with pytest.raises(
            ValueError, match="Unsupported component_type for INVERTER.*SOLAR"
        ):
            _convert_legacy_params_to_component_class(
                ComponentCategory.INVERTER, InverterType.BATTERY
            )

    def test_unsupported_inverter_no_type(self) -> None:
        """Test that INVERTER without type raises ValueError."""
        with pytest.raises(
            ValueError, match="Unsupported component_type for INVERTER.*SOLAR"
        ):
            _convert_legacy_params_to_component_class(ComponentCategory.INVERTER, None)

    def test_unsupported_category(self) -> None:
        """Test that unsupported categories raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported component_category"):
            _convert_legacy_params_to_component_class(ComponentCategory.METER, None)


class TestPowerManagingActorDeprecation:
    """Test PowerManagingActor deprecated parameter handling."""

    @staticmethod
    def _create_minimal_actor_params() -> dict[str, Any]:
        """Create minimal parameters for PowerManagingActor initialization."""
        proposals_channel: Broadcast[Proposal] = Broadcast[Any](name="proposals")
        bounds_channel: Broadcast[ReportRequest] = Broadcast(name="bounds")
        requests_channel: Broadcast[Any] = Broadcast(name="requests")
        results_channel: Broadcast[Any] = Broadcast(name="results")

        return {
            "proposals_receiver": proposals_channel.new_receiver(),
            "bounds_subscription_receiver": bounds_channel.new_receiver(),
            "power_distributing_requests_sender": requests_channel.new_sender(),
            "power_distributing_results_receiver": results_channel.new_receiver(),
            "channel_registry": ChannelRegistry(name="test"),
            "algorithm": Algorithm.MATRYOSHKA,
            "default_power": DefaultPower.ZERO,
        }

    @staticmethod
    def assert_class(actor: PowerManagingActor, expected_class: type) -> None:
        """Assert that the actor's component class matches the expected class."""
        assert (
            actor._component_class == expected_class  # pylint: disable=protected-access
        )

    def test_new_param_works_without_warning(self) -> None:
        """Test that using component_class works without warnings."""
        params = self._create_minimal_actor_params()
        params["component_class"] = Battery

        # Should not raise any warnings - use simplefilter("error") to catch them
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            actor = PowerManagingActor(**params)

        self.assert_class(actor, Battery)

    def test_deprecated_battery_param_with_warning(self) -> None:
        """Test that deprecated parameters work but emit warning for BATTERY."""
        params = self._create_minimal_actor_params()
        params["component_category"] = ComponentCategory.BATTERY

        with pytest.deprecated_call():
            actor = PowerManagingActor(**params)

        self.assert_class(actor, Battery)

    def test_deprecated_ev_charger_param_with_warning(self) -> None:
        """Test that deprecated parameters work but emit warning for EV_CHARGER."""
        params = self._create_minimal_actor_params()
        params["component_category"] = ComponentCategory.EV_CHARGER

        with pytest.deprecated_call():
            actor = PowerManagingActor(**params)

        self.assert_class(actor, EvCharger)

    def test_deprecated_solar_inverter_param_with_warning(self) -> None:
        """Test that deprecated parameters work but emit warning for SOLAR inverter."""
        params = self._create_minimal_actor_params()
        params["component_category"] = ComponentCategory.INVERTER
        params["component_type"] = InverterType.SOLAR

        with pytest.deprecated_call():
            actor = PowerManagingActor(**params)

        self.assert_class(actor, SolarInverter)

    def test_mixing_old_and_new_params_raises_error(self) -> None:
        """Test that mixing old and new parameters raises ValueError."""
        params = self._create_minimal_actor_params()
        params["component_class"] = Battery
        params["component_category"] = ComponentCategory.BATTERY

        with pytest.raises(
            ValueError,
            match="Cannot specify both 'component_class' and deprecated parameters",
        ):
            PowerManagingActor(**params)

    def test_no_params_raises_error(self) -> None:
        """Test that providing no component parameters raises ValueError."""
        params = self._create_minimal_actor_params()

        with pytest.raises(
            ValueError,
            match="Must specify either 'component_class' or deprecated parameters",
        ):
            PowerManagingActor(**params)

    def test_component_type_without_category_raises_error(self) -> None:
        """Test that component_type without component_category raises ValueError."""
        params = self._create_minimal_actor_params()
        params["component_type"] = InverterType.SOLAR

        with pytest.raises(
            ValueError,
            match="If 'component_type' is specified, 'component_category' must also be specified",
        ):
            PowerManagingActor(**params)

    def test_unsupported_inverter_type_raises_error(self) -> None:
        """Test that unsupported inverter type raises ValueError."""
        params = self._create_minimal_actor_params()
        params["component_category"] = ComponentCategory.INVERTER
        params["component_type"] = InverterType.BATTERY

        with pytest.raises(
            ValueError, match="Unsupported component_type for INVERTER.*SOLAR"
        ):
            PowerManagingActor(**params)

    def test_unsupported_category_raises_error(self) -> None:
        """Test that unsupported component category raises ValueError."""
        params = self._create_minimal_actor_params()
        params["component_category"] = ComponentCategory.METER

        with pytest.raises(ValueError, match="Unsupported component_category"):
            PowerManagingActor(**params)
