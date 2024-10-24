# Frequenz Python SDK Release Notes

## Summary

This release represents 3 months of work so it includes a lot of changes. Most of them are (breaking) API changes, in the hopes to make a more consistent and easier to use SDK 1.0. There are also quite a few bug fixes and a couple of new features.

## Upgrading

- The `BatteryPool.power_status` method now streams objects of type `BatteryPoolReport`, replacing the previous `Report` objects.

- `Channels` has been upgraded to version 1.0.0b2, for information on how to upgrade please read [Channels release notes](https://github.com/frequenz-floss/frequenz-channels-python/releases/tag/v1.0.0-beta.2).

- In `BatteryPoolReport.distribution_result`,
  * the following fields have been renamed:
    + `Result.succeeded_batteries` → `Result.succeeded_components`
    + `Result.failed_batteries` → `Result.failed_components`
    + `Request.batteries` → `Request.component_ids`
  * and the following fields are now type-hinted as `collections.abc.Set`, to clearly indicate that they are read-only:
    + `Result.succeeded_components`
    + `Result.failed_components`


- The `Fuse` class has been moved to the `frequenz.sdk.timeseries` module.

- `microgrid.grid()`
  - A `Grid` object is always instantiated now, even if the microgrid is not connected to the grid (islanded microgrids).
  - The rated current of the grid fuse is set to `Current.zero()` in case of islanded microgrids.
  - The grid fuse is set to `None` when the grid connection component metadata lacks information about the fuse.
  - Grid power and current metrics were moved from `microgrid.logical_meter()` to `microgrid.grid()`.

    Previously,

    ```python
    logical_meter = microgrid.logical_meter()
    grid_power_recv = logical_meter.grid_power.new_receiver()
    grid_current_recv = logical_meter.grid_current.new_receiver()
    ```

    Now,

    ```python
    grid = microgrid.grid()
    grid_power_recv = grid.power.new_receiver()
    grid_current_recv = grid.current.new_receiver()
    ```

- Consumer and producer power formulas were moved from `microgrid.logical_meter()` to `microgrid.consumer()` and `microgrid.producer()`, respectively.

    Previously,

    ```python
    logical_meter = microgrid.logical_meter()
    consumer_power_recv = logical_meter.consumer_power.new_receiver()
    producer_power_recv = logical_meter.producer_power.new_receiver()
    ```

    Now,

    ```python
    consumer_power_recv = microgrid.consumer().power.new_receiver()
    producer_power_recv = microgrid.producer().power.new_receiver()
    ```

- The `ComponentGraph.components()` parameters `component_id` and `component_category` were renamed to `component_ids` and `component_categories`, respectively.

- The `GridFrequency.component` property was renamed to `GridFrequency.source`

- The `microgrid.frequency()` method no longer supports passing the `component` parameter. Instead the best component is automatically selected.

- The `actor.ChannelRegistry` was rewritten to be type-aware and just a container of channels. You now need to provide the type of message that will be contained by the channel and use the `get_or_create()` method to get a channel and the `stop_and_remove()` method to stop and remove a channel. Once you get a channel you can create new senders and receivers, or set channel options, as usual. Please read the docs for a full description, but in general this:

    ```python
    r = registry.new_receiver(name)
    s = registry.new_sender(name)
    ```

    Should be replaced by:

    ```python
    r = registry.get_or_create(T, name).new_receiver()
    s = registry.get_or_create(T, name).new_sender()
    ```

- The `ReceiverFetcher` interface was slightly changed to make `maxsize` a keyword-only argument. This is to make it compatible with the `Broadcast` channel, so it can be considered a `ReceiverFetcher`.

## New Features

- A new method `microgrid.voltage()` was added to allow easy access to the phase-to-neutral 3-phase voltage of the microgrid.

- The `actor.ChannelRegistry` is now type-aware.

- A new class method `Quantity.from_string()` has been added to allow the creation of `Quantity` objects from strings.

## Bug Fixes

- 0W power requests are now not adjusted to exclusion bounds by the `PowerManager` and `PowerDistributor`, and are sent over to the microgrid API directly.

- `microgrid.frequency()` / `GridFrequency`:

  * Fix sent samples to use `Frequency` objects instead of raw `Quantity`.
  * Handle `None` values in the received samples properly.
  * Convert `nan` values in the received samples to `None`.

- The resampler now properly handles sending zero values.

  A bug made the resampler interpret zero values as `None` when generating new samples, so if the result of the resampling is zero, the resampler would just produce `None` values.

- The PowerManager no longer holds on to proposals from dead actors forever.  If an actor hasn't sent a new proposal in 60 seconds, the available proposal from that actor is dropped.

- Fix `Quantity.__format__()` sometimes skipping the number for very small values.

- Not strictly a bug fix, but the microgrid API version was bumped to v0.15.3, which indirectly bumps the common API dependency to v0.5.x, so the SDK can be compatible with other APIs using a newer version of the common API.

  Downstream projects that require a `frequenz-api-common` v0.5.x and want to ensure proper dependency resolution should update their minimum SDK version to this release.
