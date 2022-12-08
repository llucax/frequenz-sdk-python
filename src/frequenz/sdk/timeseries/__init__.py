# License: MIT
# Copyright © 2022 Frequenz Energy-as-a-Service GmbH

"""
Handling of timeseries streams.

A timeseries is a stream (normally an async iterator) of
[samples][frequenz.sdk.timeseries.Sample].

This module provides tools to operate on timeseries.

In general timeseries samples don't necessarily come at periodic intervals. To
normalize timeseries to produce `Sample`s at regular periodic intervals,
a [`Resampler`][frequenz.sdk.timeseries.resampling.Resampler] can be used.

A `Resampler` uses
a [`ResamplingFunction`][frequenz.sdk.timeseries.resampling.ResamplingFunction]
to produce a new sample from samples received in the past. If there are no
samples coming to a resampled timeseries for a while, eventually the
`Resampler` will produce `Sample`s with `None` as value, meaning there is no
way to produce meaningful samples with the available data.
"""

from ._base_types import Sample

__all__ = [
    "Sample",
]
