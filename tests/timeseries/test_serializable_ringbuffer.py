# License: MIT
# Copyright © 2023 Frequenz Energy-as-a-Service GmbH

"""Tests for the `SerializableRingBuffer` class."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pytest

from frequenz.sdk.timeseries import Sample
from frequenz.sdk.timeseries._serializable_ringbuffer import SerializableRingBuffer

FIVE_MINUTES = timedelta(minutes=5)
_29_DAYS = 60 * 24 * 29
ONE_MINUTE = timedelta(minutes=1)


def load_dump_test(dumped: SerializableRingBuffer[Any]) -> None:
    """Test ordered ring buffer."""
    size = dumped.maxlen

    random.seed(0)

    # Fill with data so we have something to compare
    # Avoiding .update() because it takes very long for 40k entries
    for i in range(size):
        dumped[i] = i

    # But use update a bit so the timestamp and gaps are initialized
    for i in range(0, size, 100):
        dumped.update(
            Sample(datetime.fromtimestamp(200 + i * FIVE_MINUTES.total_seconds()), i)
        )

    dumped.dump()

    # Load old data
    # pylint: disable=protected-access
    loaded = SerializableRingBuffer.load(dumped._path)
    assert loaded is not None

    np.testing.assert_equal(dumped[:], loaded[:])

    # pylint: disable=protected-access
    assert dumped._datetime_oldest == loaded._datetime_oldest
    # pylint: disable=protected-access
    assert dumped._datetime_newest == loaded._datetime_newest
    # pylint: disable=protected-access
    assert len(dumped._gaps) == len(loaded._gaps)
    # pylint: disable=protected-access
    assert dumped._gaps == loaded._gaps
    # pylint: disable=protected-access
    assert dumped._time_range == loaded._time_range
    # pylint: disable=protected-access
    assert dumped._sampling_period == loaded._sampling_period
    # pylint: disable=protected-access
    assert dumped._time_index_alignment == loaded._time_index_alignment


def test_load_dump_short(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Short test to perform loading & dumping."""
    tmpdir = tmp_path_factory.mktemp("load_dump")

    load_dump_test(
        SerializableRingBuffer(
            [0.0] * int(24 * FIVE_MINUTES.total_seconds()),
            FIVE_MINUTES,
            f"{tmpdir}/test_list.bin",
            datetime(2, 2, 2),
        )
    )

    load_dump_test(
        SerializableRingBuffer(
            np.empty(shape=(24 * int(FIVE_MINUTES.total_seconds()),), dtype=np.float64),
            FIVE_MINUTES,
            f"{tmpdir}/test_array.bin",
            datetime(2, 2, 2),
        )
    )


def test_load_dump(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test to load/dump 29 days of 1-minute samples."""
    tmpdir = tmp_path_factory.mktemp("load_dump")

    load_dump_test(
        SerializableRingBuffer(
            [0.0] * _29_DAYS,
            ONE_MINUTE,
            f"{tmpdir}/test_list_29.bin",
            datetime(2, 2, 2),
        )
    )

    load_dump_test(
        SerializableRingBuffer(
            np.empty(shape=(_29_DAYS,), dtype=np.float64),
            ONE_MINUTE,
            f"{tmpdir}/test_array_29.bin",
            datetime(2, 2, 2),
        )
    )