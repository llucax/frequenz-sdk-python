# Frequenz Python SDK Release Notes

## Summary

<!-- Here goes a general summary of what this release is about -->

## Upgrading

- The SDK now depends on the `frequenz-client-microgrid` v0.7.x series. The main change is now all component and microgrid IDs need to be passed using the wrapper classes `ComponentId`/`MicrogridId` instead of `int`.

## New Features

<!-- Here goes the main new features and examples or instructions on how to use them -->

## Bug Fixes

- Fix `MetricFetcher` leaks when a requested metric fetcher already existed.
