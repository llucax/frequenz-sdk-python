# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Tests for the `PVPool`."""

import asyncio
from unittest.mock import MagicMock

from frequenz.channels import Broadcast
from frequenz.client.common.microgrid.components import ComponentId
from frequenz.quantities import Power

from frequenz.sdk import timeseries
from frequenz.sdk.microgrid._power_managing import ReportRequest, _Report
from frequenz.sdk.timeseries.pv_pool._pv_pool import PVPool


def _new_power_status_report(target_power_watts: float) -> _Report:
    """Create a distinct report for power status assertions."""
    target_power = Power.from_watts(target_power_watts)
    return _Report(
        target_power=target_power,
        _inclusion_bounds=timeseries.Bounds(target_power, target_power),
        _exclusion_bounds=None,
    )


async def test_power_status_same_instance_subscriptions_work() -> None:
    """Ensure same-instance power_status subscriptions don't race each other."""
    requests_channel = Broadcast[ReportRequest](name="pv-pool-requests")
    requests_rx = requests_channel.new_receiver()
    mock_ref_store = MagicMock()
    mock_ref_store.component_ids = frozenset({ComponentId(28), ComponentId(38)})
    mock_ref_store.power_manager_bounds_subs_sender = requests_channel.new_sender()
    mock_ref_store.power_bounds_subs = {}

    pool = PVPool(pool_ref_store=mock_ref_store, name="pv-pool", priority=5)

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
