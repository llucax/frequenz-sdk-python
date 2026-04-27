# License: MIT
# Copyright © 2023 Frequenz Energy-as-a-Service GmbH

"""Tests for the `EVChargerPool`."""


import asyncio
from unittest.mock import MagicMock

from frequenz.channels import Broadcast
from frequenz.client.common.microgrid.components import ComponentId
from frequenz.quantities import Power
from pytest_mock import MockerFixture

from frequenz.sdk import microgrid, timeseries
from frequenz.sdk.microgrid._power_managing import ReportRequest, _Report
from frequenz.sdk.timeseries.ev_charger_pool._ev_charger_pool import EVChargerPool
from tests.timeseries.mock_microgrid import MockMicrogrid


def _new_power_status_report(target_power_watts: float) -> _Report:
    """Create a distinct report for power status assertions."""
    target_power = Power.from_watts(target_power_watts)
    return _Report(
        target_power=target_power,
        _inclusion_bounds=timeseries.Bounds(target_power, target_power),
        _exclusion_bounds=None,
    )


class TestEVChargerPool:
    """Tests for the `EVChargerPool`."""

    async def test_ev_power(  # pylint: disable=too-many-locals
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test the ev power formula."""
        mockgrid = MockMicrogrid(grid_meter=True, mocker=mocker)
        mockgrid.add_ev_chargers(3)

        async with mockgrid:
            ev_pool = microgrid.new_ev_charger_pool(priority=5)
            power_receiver = ev_pool.power.new_receiver()

            await mockgrid.mock_resampler.send_meter_power([16.0])
            assert (await power_receiver.receive()).value == Power.from_watts(16.0)


async def test_power_status_same_instance_subscriptions_work() -> None:
    """Ensure same-instance power_status subscriptions don't race each other."""
    requests_channel = Broadcast[ReportRequest](name="ev-pool-requests")
    requests_rx = requests_channel.new_receiver()
    mock_ref_store = MagicMock()
    mock_ref_store.component_ids = frozenset({ComponentId(12), ComponentId(22)})
    mock_ref_store.power_manager_bounds_subs_sender = requests_channel.new_sender()
    mock_ref_store.power_bounds_subs = {}

    pool = EVChargerPool(pool_ref_store=mock_ref_store, name="ev-pool", priority=5)

    first_status_rx = pool.power_status.new_receiver()
    second_status_rx = pool.power_status.new_receiver()

    await asyncio.sleep(0)

    first_request = await asyncio.wait_for(requests_rx.receive(), timeout=1.0)
    second_request = await asyncio.wait_for(requests_rx.receive(), timeout=1.0)

    report_channel = Broadcast[_Report](name="test-report", resend_latest=True)
    await first_request.report_stream_sender.send(report_channel.new_receiver())
    await second_request.report_stream_sender.send(report_channel.new_receiver())

    await asyncio.sleep(0)

    await report_channel.new_sender().send(_new_power_status_report(123.0))

    first_report = await asyncio.wait_for(first_status_rx.receive(), timeout=1.0)
    second_report = await asyncio.wait_for(second_status_rx.receive(), timeout=1.0)
    assert first_report.target_power == Power.from_watts(123.0)
    assert second_report.target_power == Power.from_watts(123.0)
