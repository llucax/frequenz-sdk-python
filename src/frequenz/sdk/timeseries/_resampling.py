# License: MIT
# Copyright © 2022 Frequenz Energy-as-a-Service GmbH

"""Timeseries resampler."""

from __future__ import annotations

import asyncio
import itertools
import logging
import math
from bisect import bisect
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Callable, Coroutine, Optional, Sequence

from frequenz.channels.util import Timer

from .._internal.asyncio import cancel_and_await
from . import Sample

_logger = logging.getLogger(__name__)


DEFAULT_BUFFER_LEN_INIT = 16
"""Default initial buffer length.

Buffers will be created initially with this length, but they could grow or
shrink depending on the source properties, like sampling rate, to make
sure all the requested past sampling periods can be stored.
"""


DEFAULT_BUFFER_LEN_MAX = 1024
"""Default maximum allowed buffer length.

If a buffer length would get bigger than this, it will be truncated to this
length.
"""


DEFAULT_BUFFER_LEN_WARN = 128
"""Default minimum buffer length that will produce a warning.

If a buffer length would get bigger than this, a warning will be logged.
"""


Source = AsyncIterator[Sample]
"""A source for a timeseries.

A timeseries can be received sample by sample in a streaming way
using a source.
"""

Sink = Callable[[Sample], Coroutine[None, None, None]]
"""A sink for a timeseries.

A new timeseries can be generated by sending samples to a sink.

This should be an `async` callable, for example:

``` python
async some_sink(Sample) -> None:
    ...
```

Args:
    sample (Sample): A sample to be sent out.
"""


ResamplingFunction = Callable[
    [Sequence[Sample], "ResamplerConfig", "SourceProperties"], float
]
"""Resampling function type.

A resampling function produces a new sample based on a list of pre-existing
samples. It can do "upsampling" when there data rate of the `input_samples`
period is smaller than the `resampling_period_s`, or "downsampling" if it is
bigger.

In general a resampling window is the same as the `resampling_period_s`, and
this function might receive input samples from multiple windows in the past to
enable extrapolation, but no samples from the future (so the timestamp of the
new sample that is going to be produced will always be bigger than the biggest
timestamp in the input data).

Args:
    input_samples (Sequence[Sample]): The sequence of pre-existing samples.
    resampler_config (ResamplerConfig): The configuration of the resampling
        calling this function.
    source_properties (SourceProperties): The properties of the source being
        resampled.

Returns:
    new_sample (float): The value of new sample produced after the resampling.
"""


# pylint: disable=unused-argument
def average(
    samples: Sequence[Sample],
    resampler_config: ResamplerConfig,
    source_properties: SourceProperties,
) -> float:
    """Calculate average of all the provided values.

    Args:
        samples: The samples to apply the average to. It must be non-empty.
        resampler_config: The configuration of the resampler calling this
            function.
        source_properties: The properties of the source being resampled.

    Returns:
        The average of all `samples` values.
    """
    assert len(samples) > 0, "Average cannot be given an empty list of samples"
    values = list(sample.value for sample in samples if sample.value is not None)
    return sum(values) / len(values)


@dataclass(frozen=True)
class ResamplerConfig:
    """Resampler configuration."""

    resampling_period_s: float
    """The resampling period in seconds.

    This is the time it passes between resampled data should be calculated.

    It must be a positive number.
    """

    max_data_age_in_periods: float = 3.0
    """The maximum age a sample can have to be considered *relevant* for resampling.

    Expressed in number of periods, where period is the `resampling_period_s`
    if we are downsampling (resampling period bigger than the input period) or
    the input sampling period if we are upsampling (input period bigger than
    the resampling period).

    It must be bigger than 1.0.

    Example:
        If `resampling_period_s` is 3, the input sampling period is
        1 and `max_data_age_in_periods` is 2, then data older than 3*2
        = 6 seconds will be discarded when creating a new sample and never
        passed to the resampling function.

        If `resampling_period_s` is 3, the input sampling period is
        5 and `max_data_age_in_periods` is 2, then data older than 5*2
        = 10 seconds will be discarded when creating a new sample and never
        passed to the resampling function.
    """

    resampling_function: ResamplingFunction = average
    """The resampling function.

    This function will be applied to the sequence of relevant samples at
    a given time. The result of the function is what is sent as the resampled
    value.
    """

    initial_buffer_len: int = DEFAULT_BUFFER_LEN_INIT
    """The initial length of the resampling buffer.

    The buffer could grow or shrink depending on the source properties,
    like sampling rate, to make sure all the requested past sampling periods
    can be stored.

    It must be at least 1 and at most `max_buffer_len`.
    """

    warn_buffer_len: int = DEFAULT_BUFFER_LEN_WARN
    """The minimum length of the resampling buffer that will emit a warning.

    If a buffer grows bigger than this value, it will emit a warning in the
    logs, so buffers don't grow too big inadvertently.

    It must be at least 1 and at most `max_buffer_len`.
    """

    max_buffer_len: int = DEFAULT_BUFFER_LEN_MAX
    """The maximum length of the resampling buffer.

    Buffers won't be allowed to grow beyond this point even if it would be
    needed to keep all the requested past sampling periods. An error will be
    emitted in the logs if the buffer length needs to be truncated to this
    value.

    It must be at bigger than `warn_buffer_len`.
    """

    def __post_init__(self) -> None:
        """Check that config values are valid.

        Raises:
            ValueError: If any value is out of range.
        """
        if self.resampling_period_s < 0.0:
            raise ValueError(
                f"resampling_period_s ({self.resampling_period_s}) must be positive"
            )
        if self.max_data_age_in_periods < 1.0:
            raise ValueError(
                f"max_data_age_in_periods ({self.max_data_age_in_periods}) should be at least 1.0"
            )
        if self.warn_buffer_len < 1:
            raise ValueError(
                f"warn_buffer_len ({self.warn_buffer_len}) should be at least 1"
            )
        if self.max_buffer_len <= self.warn_buffer_len:
            raise ValueError(
                f"max_buffer_len ({self.max_buffer_len}) should "
                f"be bigger than warn_buffer_len ({self.warn_buffer_len})"
            )

        if self.initial_buffer_len < 1:
            raise ValueError(
                f"initial_buffer_len ({self.initial_buffer_len}) should at least 1"
            )
        if self.initial_buffer_len > self.max_buffer_len:
            raise ValueError(
                f"initial_buffer_len ({self.initial_buffer_len}) is bigger "
                f"than max_buffer_len ({self.max_buffer_len}), use a smaller "
                "initial_buffer_len or a bigger max_buffer_len"
            )
        if self.initial_buffer_len > self.warn_buffer_len:
            _logger.warning(
                "initial_buffer_len (%s) is bigger than warn_buffer_len (%s)",
                self.initial_buffer_len,
                self.warn_buffer_len,
            )


class SourceStoppedError(RuntimeError):
    """A timeseries stopped producing samples."""

    def __init__(self, source: Source) -> None:
        """Create an instance.

        Args:
            source: The source of the timeseries that stopped producing samples.
        """
        super().__init__(f"Timeseries stopped producing samples, source: {source}")
        self.source = source
        """The source of the timeseries that stopped producing samples."""

    def __repr__(self) -> str:
        """Return the representation of the instance.

        Returns:
            The representation of the instance.
        """
        return f"{self.__class__.__name__}({self.source!r})"


class ResamplingError(RuntimeError):
    """An Error ocurred while resampling.

    This error is a container for errors raised by the underlying sources and
    or sinks.
    """

    def __init__(
        self, exceptions: dict[Source, Exception | asyncio.CancelledError]
    ) -> None:
        """Create an instance.

        Args:
            exceptions: A mapping of timeseries source and the exception
                encountered while resampling that timeseries. Note that the
                error could be raised by the sink, while trying to send
                a resampled data for this timeseries, the source key is only
                used to identify the timeseries with the issue, it doesn't
                necessarily mean that the error was raised by the source. The
                underlying exception should provide information about what was
                the actual source of the exception.
        """
        super().__init__(f"Some error were found while resampling: {exceptions}")
        self.exceptions = exceptions
        """A mapping of timeseries source and the exception encountered.

        Note that the error could be raised by the sink, while trying to send
        a resampled data for this timeseries, the source key is only used to
        identify the timeseries with the issue, it doesn't necessarily mean
        that the error was raised by the source. The underlying exception
        should provide information about what was the actual source of the
        exception.
        """

    def __repr__(self) -> str:
        """Return the representation of the instance.

        Returns:
            The representation of the instance.
        """
        return f"{self.__class__.__name__}({self.exceptions=})"


@dataclass
class SourceProperties:
    """Properties of a resampling source."""

    sampling_start: Optional[datetime] = None
    """The time when resampling started for this source.

    `None` means it didn't started yet.
    """

    received_samples: int = 0
    """Total samples received by this source so far."""

    sampling_period_s: Optional[float] = None
    """The sampling period of this source (in seconds).

    This is we receive (on average) one sample for this source every
    `sampling_period_s` seconds.

    `None` means it is unknown.
    """


class Resampler:
    """A timeseries resampler.

    In general timeseries [`Source`][frequenz.sdk.timeseries.Source]s don't
    necessarily come at periodic intervals. You can use this class to normalize
    timeseries to produce `Sample`s at regular periodic intervals.

    This class uses
    a [`ResamplingFunction`][frequenz.sdk.timeseries.resampling.ResamplingFunction]
    to produce a new sample from samples received in the past. If there are no
    samples coming to a resampled timeseries for a while, eventually the
    `Resampler` will produce `Sample`s with `None` as value, meaning there is
    no way to produce meaningful samples with the available data.
    """

    def __init__(self, config: ResamplerConfig) -> None:
        """Initialize an instance.

        Args:
            config: The configuration for the resampler.
        """
        self._config = config
        """The configuration for this resampler."""

        self._resamplers: dict[Source, _StreamingHelper] = {}
        """A mapping between sources and the streaming helper handling that source."""

        self._timer: Timer = Timer(config.resampling_period_s)
        """The timer to trigger the next resampling."""

        self._window_end: datetime = datetime.now(timezone.utc) + timedelta(
            seconds=self._config.resampling_period_s
        )
        """The time in which the current window ends.

        This is used to make sure every resampling window is generated at
        precise times. We can't rely on the timer timestamp because timers will
        never fire at the exact requested time, so if we don't use a precise
        time for the end of the window, the resampling windows we produce will
        have different sizes.
        """

    @property
    def config(self) -> ResamplerConfig:
        """Get the resampler configuration.

        Returns:
            The resampler configuration.
        """
        return self._config

    def get_source_properties(self, source: Source) -> SourceProperties:
        """Get the properties of a timeseries source.

        Args:
            source: The source from which to get the properties.

        Returns:
            The timeseries source properties.
        """
        return self._resamplers[source].source_properties

    async def stop(self) -> None:
        """Cancel all receiving tasks."""
        await asyncio.gather(*[helper.stop() for helper in self._resamplers.values()])

    def add_timeseries(self, name: str, source: Source, sink: Sink) -> bool:
        """Start resampling a new timeseries.

        Args:
            name: The name of the timeseries (for logging purposes).
            source: The source of the timeseries to resample.
            sink: The sink to use to send the resampled data.

        Returns:
            `True` if the timeseries was added, `False` if the timeseries was
            not added because there already a timeseries using the provided
            receiver.
        """
        if source in self._resamplers:
            return False

        resampler = _StreamingHelper(
            _ResamplingHelper(name, self._config), source, sink
        )
        self._resamplers[source] = resampler
        return True

    def remove_timeseries(self, source: Source) -> bool:
        """Stop resampling the timeseries produced by `source`.

        Args:
            source: The source of the timeseries to stop resampling.

        Returns:
            `True` if the timeseries was removed, `False` if nothing was
                removed (because the a timeseries with that `source` wasn't
                being resampled).
        """
        try:
            del self._resamplers[source]
        except KeyError:
            return False
        return True

    async def _wait_for_next_resampling_period(self) -> None:
        """Wait for next resampling period.

        If resampling period already started, then return without sleeping.
        That would allow us to catch up with resampling.
        Print warning if function woke up to late.
        """
        now = datetime.now(tz=timezone.utc)
        if self._window_end > now:
            sleep_for = self._window_end - now
            await asyncio.sleep(sleep_for.total_seconds())

        timer_error_s = (now - self._window_end).total_seconds()
        if timer_error_s > (self._config.resampling_period_s / 10.0):
            _logger.warning(
                "The resampling task woke up too late. Resampling should have started "
                "at %s, but it started at %s (%s seconds difference; resampling "
                "period is %s seconds)",
                self._window_end,
                now,
                timer_error_s,
                self._config.resampling_period_s,
            )

    async def resample(self, *, one_shot: bool = False) -> None:
        """Start resampling all known timeseries.

        This method will run forever unless there is an error while receiving
        from a source or sending to a sink (or `one_shot` is used).

        Args:
            one_shot: Wether the resampling should run only for one resampling
                period.

        Raises:
            ResamplingError: If some timeseries source or sink encounters any
                errors while receiving or sending samples. In this case the
                timer still runs and the timeseries will keep receiving data.
                The user should remove (and re-add if desired) the faulty
                timeseries from the resampler before calling this method
                again).
        """
        while True:
            await self._wait_for_next_resampling_period()

            results = await asyncio.gather(
                *[r.resample(self._window_end) for r in self._resamplers.values()],
                return_exceptions=True,
            )

            self._window_end = self._window_end + timedelta(
                seconds=self._config.resampling_period_s
            )
            exceptions = {
                source: results[i]
                for i, source in enumerate(self._resamplers)
                # CancelledError inherits from BaseException, but we don't want
                # to catch *all* BaseExceptions here.
                if isinstance(results[i], (Exception, asyncio.CancelledError))
            }
            if exceptions:
                raise ResamplingError(exceptions)
            if one_shot:
                break


class _ResamplingHelper:
    """Keeps track of *relevant* samples to pass them to the resampling function.

    Samples are stored in an internal ring buffer. All collected samples that
    are newer than `max(resampling_period_s, input_period_s)
    * max_data_age_in_periods` seconds are considered *relevant* and are passed
    to the provided `resampling_function` when calling the `resample()` method.
    All older samples are discarded.
    """

    def __init__(self, name: str, config: ResamplerConfig) -> None:
        """Initialize an instance.

        Args:
            name: The name of this resampler helper (for logging purposes).
            config: The configuration for this resampler helper.
        """
        self._name = name
        self._config = config
        self._buffer: deque[Sample] = deque(maxlen=config.initial_buffer_len)
        self._source_properties: SourceProperties = SourceProperties()

    @property
    def source_properties(self) -> SourceProperties:
        """Return the properties of the source.

        Returns:
            The properties of the source.
        """
        return self._source_properties

    def add_sample(self, sample: Sample) -> None:
        """Add a new sample to the internal buffer.

        Args:
            sample: The sample to be added to the buffer.
        """
        self._buffer.append(sample)
        if self._source_properties.sampling_start is None:
            self._source_properties.sampling_start = sample.timestamp
        self._source_properties.received_samples += 1

    def _update_source_sample_period(self, now: datetime) -> bool:
        """Update the source sample period.

        Args:
            now: The datetime in which this update happens.

        Returns:
            Whether the source sample period was changed (was really updated).
        """
        assert (
            self._buffer.maxlen is not None and self._buffer.maxlen > 0
        ), "We need a maxlen of at least 1 to update the sample period"

        config = self._config
        props = self._source_properties

        # We only update it if we didn't before and we have enough data
        if (
            props.sampling_period_s is not None
            or props.sampling_start is None
            or props.received_samples
            < config.resampling_period_s * config.max_data_age_in_periods
            or len(self._buffer) < self._buffer.maxlen
            # There might be a race between the first sample being received and
            # this function being called
            or now <= props.sampling_start
        ):
            return False

        samples_time_delta = now - props.sampling_start
        props.sampling_period_s = (
            samples_time_delta.total_seconds()
        ) / props.received_samples

        _logger.debug(
            "New input sampling period calculated for %r: %ss",
            self._name,
            props.sampling_period_s,
        )
        return True

    def _update_buffer_len(self) -> bool:
        """Update the length of the buffer based on the source properties.

        Returns:
            Whether the buffer length was changed (was really updated).
        """
        input_sampling_period_s = self._source_properties.sampling_period_s

        # To make type checking happy
        assert input_sampling_period_s is not None
        assert self._buffer.maxlen is not None

        config = self._config

        # If we are upsampling, one sample could be enough for back-filling, but
        # we store max_data_age_in_periods for input periods, so resampling
        # functions can do more complex inter/extrapolation if they need to.
        if input_sampling_period_s > config.resampling_period_s:
            new_buffer_len = input_sampling_period_s * config.max_data_age_in_periods
        # If we are upsampling, we want a buffer that can hold
        # max_data_age_in_periods * resampling_period_s seconds of data, and we
        # one sample every input_sampling_period_s.
        else:
            new_buffer_len = (
                config.resampling_period_s
                / input_sampling_period_s
                * config.max_data_age_in_periods
            )

        new_buffer_len = max(1, math.ceil(new_buffer_len))
        if new_buffer_len > config.max_buffer_len:
            _logger.error(
                "The new buffer length (%s) for timeseries %s is too big, using %s instead",
                new_buffer_len,
                self._name,
                config.max_buffer_len,
            )
            new_buffer_len = config.max_buffer_len
        elif new_buffer_len > config.warn_buffer_len:
            _logger.warning(
                "The new buffer length (%s) for timeseries %s bigger than %s",
                new_buffer_len,
                self._name,
                config.warn_buffer_len,
            )

        if new_buffer_len == self._buffer.maxlen:
            return False

        _logger.debug(
            "New buffer length calculated for %r: %s",
            self._name,
            new_buffer_len,
        )

        self._buffer = deque(self._buffer, maxlen=new_buffer_len)

        return True

    def resample(self, timestamp: datetime) -> Sample:
        """Generate a new sample based on all the current *relevant* samples.

        Args:
            timestamp: The timestamp to be used to calculate the new sample.

        Returns:
            A new sample generated by calling the resampling function with all
                the current *relevant* samples in the internal buffer, if any.
                If there are no *relevant* samples, then the new sample will
                have `None` as `value`.
        """
        if self._update_source_sample_period(timestamp):
            self._update_buffer_len()

        conf = self._config
        props = self._source_properties

        # To see which samples are relevant we need to consider if we are down
        # or upsampling.
        period = (
            max(conf.resampling_period_s, props.sampling_period_s)
            if props.sampling_period_s is not None
            else conf.resampling_period_s
        )
        minimum_relevant_timestamp = timestamp - timedelta(
            seconds=period * conf.max_data_age_in_periods
        )

        # We need to pass a dummy Sample to bisect because it only support
        # specifying a key extraction function in Python 3.10, so we need to
        # compare samples at the moment.
        min_index = bisect(self._buffer, Sample(minimum_relevant_timestamp, None))
        max_index = bisect(self._buffer, Sample(timestamp, None))
        # Using itertools for slicing doesn't look very efficient, but
        # experiments with a custom (ring) buffer that can slice showed that
        # it is not that bad. See:
        # https://github.com/frequenz-floss/frequenz-sdk-python/pull/130
        # So if we need more performance beyond this point, we probably need to
        # resort to some C (or similar) implementation.
        relevant_samples = list(itertools.islice(self._buffer, min_index, max_index))
        value = (
            conf.resampling_function(relevant_samples, conf, props)
            if relevant_samples
            else None
        )
        return Sample(timestamp, value)


class _StreamingHelper:
    """Resample data coming from a source, sending the results to a sink."""

    def __init__(
        self,
        helper: _ResamplingHelper,
        source: Source,
        sink: Sink,
    ) -> None:
        """Initialize an instance.

        Args:
            helper: The helper instance to use to resample incoming data.
            source: The source to use to get the samples to be resampled.
            sink: The sink to use to send the resampled data.
        """
        self._helper: _ResamplingHelper = helper
        self._source: Source = source
        self._sink: Sink = sink
        self._receiving_task: asyncio.Task[None] = asyncio.create_task(
            self._receive_samples()
        )

    @property
    def source_properties(self) -> SourceProperties:
        """Get the source properties.

        Returns:
            The source properties.
        """
        return self._helper.source_properties

    async def stop(self) -> None:
        """Cancel the receiving task."""
        await cancel_and_await(self._receiving_task)

    async def _receive_samples(self) -> None:
        """Pass received samples to the helper.

        This method keeps running until the source stops (or fails with an
        error).
        """
        async for sample in self._source:
            if sample.value is not None and not math.isnan(sample.value):
                self._helper.add_sample(sample)

    async def resample(self, timestamp: datetime) -> None:
        """Calculate a new sample for the passed `timestamp` and send it.

        The helper is used to calculate the new sample and the sender is used
        to send it.

        Args:
            timestamp: The timestamp to be used to calculate the new sample.

        Raises:
            SourceStoppedError: If the source stopped sending samples.
            Exception: if there was any error while receiving from the source
                or sending to the sink.

                If the error was in the source, then this helper will stop
                working, as the internal task to receive samples will stop due
                to the exception. Any subsequent call to `resample()` will keep
                raising the same exception.

                If the error is in the sink, the receiving part will continue
                working while this helper is alive.

        # noqa: DAR401 recv_exception
        """
        if self._receiving_task.done():
            if recv_exception := self._receiving_task.exception():
                raise recv_exception
            raise SourceStoppedError(self._source)

        await self._sink(self._helper.resample(timestamp))
