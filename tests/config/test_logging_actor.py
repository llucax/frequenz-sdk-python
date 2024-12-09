# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Tests for logging config updater."""

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import pytest
from frequenz.channels import Broadcast
from marshmallow import ValidationError
from pytest_mock import MockerFixture

from frequenz.sdk.config import (
    LoggerConfig,
    LoggingConfig,
    LoggingConfigUpdatingActor,
    load_config,
)


def test_logging_config() -> None:
    """Test if logging config is correctly loaded."""
    config_raw = {
        "root_logger": {"level": "DEBUG"},
        "loggers": {
            "frequenz.sdk.actor": {"level": "INFO"},
            "frequenz.sdk.timeseries": {"level": "ERROR"},
        },
    }
    config = LoggingConfig(
        root_logger=LoggerConfig(level="DEBUG"),
        loggers={
            "frequenz.sdk.actor": LoggerConfig(level="INFO"),
            "frequenz.sdk.timeseries": LoggerConfig(level="ERROR"),
        },
    )

    assert load_config(LoggingConfig, config_raw) == config

    config_raw = {}
    config = LoggingConfig()
    assert load_config(LoggingConfig, config_raw) == config

    config_raw = {"root_logger": {"level": "UNKNOWN"}}
    with pytest.raises(ValidationError):
        load_config(LoggingConfig, config_raw)

    config_raw = {"unknown": {"frequenz.sdk.actor": {"level": "DEBUG"}}}
    with pytest.raises(ValidationError):
        load_config(LoggingConfig, config_raw)


@pytest.fixture
def cleanup_logs() -> Any:
    """Reset logging to default.

    Python doesn't cleanup logging configuration after tests, so we need to do it manually.
    """
    yield

    logging.getLogger("frequenz.sdk.actor").setLevel(logging.NOTSET)
    logging.getLogger("frequenz.sdk.timeseries").setLevel(logging.NOTSET)


async def test_logging_config_updating_actor(
    mocker: MockerFixture,
    cleanup_logs: Any,
) -> None:
    """Test if logging is configured and updated correctly."""
    # Mock method that sets root level logging.
    # Python doesn't cleanup logging configuration after tests.
    # Overriding logging.basicConfig would mess up other tests, so we mock it.
    # This is just for extra safety because changing root logging level in unit tests
    # is not working anyway - python ignores it.
    mocker.patch("frequenz.sdk.config._logging_actor.logging.basicConfig")

    config_channel = Broadcast[Mapping[str, Any]](name="config")
    config_sender = config_channel.new_sender()
    async with LoggingConfigUpdatingActor(
        config_recv=config_channel.new_receiver().map(
            lambda app_config: app_config.get("logging", {})
        )
    ) as actor:
        assert logging.getLogger("frequenz.sdk.actor").level == logging.NOTSET
        assert logging.getLogger("frequenz.sdk.timeseries").level == logging.NOTSET

        update_logging_spy = mocker.spy(actor, "_update_logging")

        # Send first config
        await config_sender.send(
            {
                "logging": {
                    "root_logger": {"level": "ERROR"},
                    "loggers": {
                        "frequenz.sdk.actor": {"level": "DEBUG"},
                        "frequenz.sdk.timeseries": {"level": "ERROR"},
                    },
                }
            }
        )
        await asyncio.sleep(0.01)
        update_logging_spy.assert_called_once_with(
            LoggingConfig(
                root_logger=LoggerConfig(level="ERROR"),
                loggers={
                    "frequenz.sdk.actor": LoggerConfig(level="DEBUG"),
                    "frequenz.sdk.timeseries": LoggerConfig(level="ERROR"),
                },
            )
        )
        assert logging.getLogger("frequenz.sdk.actor").level == logging.DEBUG
        assert logging.getLogger("frequenz.sdk.timeseries").level == logging.ERROR
        update_logging_spy.reset_mock()

        # Update config
        await config_sender.send(
            {
                "logging": {
                    "root_logger": {"level": "WARNING"},
                    "loggers": {
                        "frequenz.sdk.actor": {"level": "INFO"},
                    },
                }
            }
        )
        await asyncio.sleep(0.01)
        expected_config = LoggingConfig(
            root_logger=LoggerConfig(level="WARNING"),
            loggers={
                "frequenz.sdk.actor": LoggerConfig(level="INFO"),
            },
        )
        update_logging_spy.assert_called_once_with(expected_config)
        assert logging.getLogger("frequenz.sdk.actor").level == logging.INFO
        assert logging.getLogger("frequenz.sdk.timeseries").level == logging.NOTSET
        update_logging_spy.reset_mock()

        # Send invalid config to make sure actor doesn't crash and doesn't setup invalid config.
        await config_sender.send({"logging": {"root_logger": {"level": "UNKNOWN"}}})
        await asyncio.sleep(0.01)
        update_logging_spy.assert_not_called()
        assert actor._current_config == expected_config
        update_logging_spy.reset_mock()

        # Send empty config to reset logging to default
        await config_sender.send({"other": {"var1": 1}})
        await asyncio.sleep(0.01)
        update_logging_spy.assert_called_once_with(LoggingConfig())
        assert logging.getLogger("frequenz.sdk.actor").level == logging.NOTSET
        assert logging.getLogger("frequenz.sdk.timeseries").level == logging.NOTSET
        update_logging_spy.reset_mock()


async def test_default_config(
    mocker: MockerFixture,
    cleanup_logs: Any,
) -> None:
    """Test the passed default config is used before a config is received."""
    # Mock method that sets root level logging.
    # Python doesn't cleanup logging configuration after tests.
    # Overriding logging.basicConfig would mess up other tests, so we mock it.
    # This is just for extra safety because changing root logging level in unit tests
    # is not working anyway - python ignores it.
    mocker.patch("frequenz.sdk.config._logging_actor.logging.basicConfig")

    config_channel = Broadcast[Mapping[str, Any]](name="config")
    config_sender = config_channel.new_sender()

    async with LoggingConfigUpdatingActor(
        config_recv=config_channel.new_receiver().map(
            lambda app_config: app_config.get("logging", {})
        ),
        default_config=LoggingConfig(
            root_logger=LoggerConfig(level="ERROR"),
            loggers={
                "frequenz.sdk.actor": LoggerConfig(level="DEBUG"),
                "frequenz.sdk.timeseries": LoggerConfig(level="ERROR"),
            },
        ),
    ) as actor:
        # Check we start with the default config
        assert logging.getLogger("root").level == logging.ERROR
        assert logging.getLogger("frequenz.sdk.actor").level == logging.DEBUG
        assert logging.getLogger("frequenz.sdk.timeseries").level == logging.ERROR

        # Send a new config and test the default config doesn't apply anymore
        update_logging_spy = mocker.spy(actor, "_update_logging")

        # Send new config
        await config_sender.send(
            {
                "logging": {
                    "root_logger": {"level": "WARNING"},
                    "loggers": {
                        "frequenz.sdk.actor": {"level": "INFO"},
                    },
                }
            }
        )
        expected_config = LoggingConfig(
            root_logger=LoggerConfig(level="WARNING"),
            loggers={
                "frequenz.sdk.actor": LoggerConfig(level="INFO"),
            },
        )
        update_logging_spy.assert_called_once_with(expected_config)
        assert logging.getLogger("root").level == logging.WARNING
        assert logging.getLogger("frequenz.sdk.actor").level == logging.INFO
        assert logging.getLogger("frequenz.sdk.timeseries").level == logging.NOTSET
        update_logging_spy.reset_mock()
