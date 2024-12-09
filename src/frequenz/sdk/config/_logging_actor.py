# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Read and update logging severity from config."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, Final

import marshmallow
import marshmallow.validate
from frequenz.channels import Receiver

from ..actor import Actor
from ._util import load_config

_logger = logging.getLogger(__name__)

LogLevel = Annotated[
    str,
    marshmallow.fields.String(
        validate=marshmallow.validate.OneOf(choices=logging.getLevelNamesMapping())
    ),
]
"""A marshmallow field for validating log levels."""


@dataclass
class LoggerConfig:
    """A configuration for a logger."""

    level: LogLevel = field(
        default="NOTSET",
        metadata={
            "metadata": {
                "description": "Log level for the logger. Uses standard logging levels."
            },
        },
    )
    """The log level for the logger."""


@dataclass
class LoggingConfig:
    """A configuration for the logging system."""

    root_logger: LoggerConfig = field(
        default_factory=LoggerConfig,
        metadata={
            "metadata": {
                "description": "Default default configuration for all loggers.",
            },
        },
    )
    """The default log level."""

    loggers: dict[str, LoggerConfig] = field(
        default_factory=dict,
        metadata={
            "metadata": {
                "description": "Configuration for a logger (the key is the logger name)."
            },
        },
    )
    """The list of loggers configurations."""


class LoggingConfigUpdatingActor(Actor):
    """Actor that listens for logging configuration changes and sets them.

    Example:
        `config.toml` file:
        ```toml
        [logging.root_logger]
        level = "INFO"

        [logging.loggers."frequenz.sdk.actor.power_distributing"]
        level = "DEBUG"

        [logging.loggers."frequenz.channels"]
        level = "DEBUG"
        ```

        ```python
        import asyncio
        from collections.abc import Mapping
        from typing import Any

        from frequenz.channels import Broadcast
        from frequenz.sdk.config import LoggingConfigUpdatingActor, ConfigManagingActor
        from frequenz.sdk.actor import run as run_actors

        async def run() -> None:
            config_channel = Broadcast[Mapping[str, Any]](name="config", resend_latest=True)
            actors = [
                ConfigManagingActor(
                    config_paths=["config.toml"], output=config_channel.new_sender()
                ),
                LoggingConfigUpdatingActor(
                    config_recv=config_channel.new_receiver(limit=1)).map(
                        lambda app_config: app_config.get("logging", {}
                    )
                ),
            ]
            await run_actors(*actors)

        asyncio.run(run())
        ```

        Now whenever the `config.toml` file is updated, the logging configuration
        will be updated as well.
    """

    def __init__(
        self,
        *,
        config_recv: Receiver[Mapping[str, Any]],
        default_config: LoggingConfig = LoggingConfig(),
        log_datefmt: str = "%Y-%m-%dT%H:%M:%S%z",
        log_format: str = "%(asctime)s %(levelname)-8s %(name)s:%(lineno)s: %(message)s",
        name: str | None = None,
    ):
        """Initialize this instance.

        Args:
            config_recv: The receiver to listen for configuration changes.
            default_config: The default configuration for the logging system when the
                configuration is not yet available.
            log_datefmt: Use the specified date/time format in logs.
            log_format: Use the specified format string in logs.
            name: The name of this actor. If `None`, `str(id(self))` will be used. This
                is used mostly for debugging purposes.

        Note:
            The `log_format` and `log_datefmt` parameters are used in a call to
            `logging.basicConfig()`. If logging has already been configured elsewhere
            in the application (through a previous `basicConfig()` call), then the format
            settings specified here will be ignored.
        """
        self._config_recv = config_recv

        self.default_config: Final[LoggingConfig] = default_config
        """The default configuration for the logging system.

        This configuration is used when the configuration is not yet available.
        """

        # Setup default configuration.
        # This ensures logging is configured even if actor fails to start or
        # if the configuration cannot be loaded.
        self._current_config: LoggingConfig = default_config

        super().__init__(name=name)

        logging.basicConfig(
            format=log_format,
            datefmt=log_datefmt,
        )
        self._update_logging(self._current_config)

    async def _run(self) -> None:
        """Listen for configuration changes and update logging."""
        async for message in self._config_recv:
            try:
                new_config = load_config(LoggingConfig, message)
            except marshmallow.ValidationError:
                _logger.exception(
                    "Invalid logging configuration received. Skipping config update"
                )
                continue

            if new_config != self._current_config:
                self._update_logging(new_config)

    def _update_logging(self, config: LoggingConfig) -> None:
        """Configure the logging level."""
        # TODO: do _recursive_update(config, self.default_config) here

        # If the logger is not in the new config, set it to NOTSET
        loggers_to_unset = self._current_config.loggers.keys() - config.loggers.keys()
        for logger_id in loggers_to_unset:
            _logger.debug("Unsetting log level for logger '%s'", logger_id)
            logging.getLogger(logger_id).setLevel(logging.NOTSET)

        self._current_config = config
        _logger.debug(
            "Setting root logger level to '%s'", self._current_config.root_logger.level
        )
        logging.getLogger().setLevel(self._current_config.root_logger.level)

        # For each logger in the new config, set the log level
        for logger_id, logger_config in self._current_config.loggers.items():
            _logger.debug(
                "Setting log level for logger '%s' to '%s'",
                logger_id,
                logger_config.level,
            )
            logging.getLogger(logger_id).setLevel(logger_config.level)

        _logger.info("Logging config changed to: %s", self._current_config)


def _recursive_update(
    target: dict[str, Any], overrides: Mapping[str, Any]
) -> dict[str, Any]:
    """Recursively updates dictionary d1 with values from dictionary d2.

    Args:
        target: The original dictionary to be updated.
        overrides: The dictionary with updates.

    Returns:
        The updated dictionary.
    """
    for key, value in overrides.items():
        if (
            key in target
            and isinstance(target[key], MutableMapping)
            and isinstance(value, MutableMapping)
        ):
            _recursive_update(target[key], value)
        else:
            target[key] = value
    return target
