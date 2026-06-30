# License: MIT
# Copyright © 2022 Frequenz Energy-as-a-Service GmbH

"""Read and update config variables."""

import logging
import pathlib
import tomllib
from collections import abc
from collections.abc import Mapping, MutableMapping
from datetime import timedelta
from typing import Any, assert_never

from frequenz.channels import Sender
from frequenz.channels.file_watcher import EventType, FileWatcher

from ..actor._actor import Actor

_logger = logging.getLogger(__name__)


class ConfigManagingActor(Actor):
    """An actor that monitors TOML configuration files for updates.

    When the actor is started the configuration files will be read and sent to the
    output sender. Then the actor will start monitoring the files for updates. If any
    file is updated, all the configuration files will be re-read and sent to the output
    sender.

    If no configuration file could be read, the actor will raise an exception.

    The configuration files are read in the order of the paths, so the last path will
    override the configuration set by the previous paths. Dict keys will be merged
    recursively, but other objects (like lists) will be replaced by the value in the
    last path.

    Example:
        If `config1.toml` contains:

        ```toml
        var1 = [1, 2]
        var2 = 2
        [section]
        var3 = [1, 3]
        ```

        And `config2.toml` contains:

        ```toml
        var2 = "hello" # Can override with a different type too
        var3 = 4
        [section]
        var3 = 5
        var4 = 5
        ```

        Then the final configuration will be:

        ```py
        {
            "var1": [1, 2],
            "var2": "hello",
            "var3": 4,
            "section": {
                "var3": 5,
                "var4": 5,
            },
        }
        ```
    """

    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        config_paths: str | pathlib.Path | abc.Sequence[pathlib.Path | str],
        output: Sender[abc.Mapping[str, Any]],
        *,
        name: str | None = None,
        force_polling: bool = True,
        polling_interval: timedelta = timedelta(seconds=1),
    ) -> None:
        """Initialize this instance.

        Args:
            config_paths: The paths to the TOML files with the configuration. Order
                matters, as the configuration will be read and updated in the order
                of the paths, so the last path will override the configuration set by
                the previous paths. Dict keys will be merged recursively, but other
                objects (like lists) will be replaced by the value in the last path.
            output: The sender to send the configuration to.
            name: The name of the actor. If `None`, `str(id(self))` will
                be used. This is used mostly for debugging purposes.
            force_polling: Whether to force file polling to check for changes.
            polling_interval: The interval to poll for changes. Only relevant if
                polling is enabled.

        Raises:
            ValueError: If no configuration path is provided.
        """
        super().__init__(name=name)
        match config_paths:
            case str():
                self._config_paths = [pathlib.Path(config_paths)]
            case pathlib.Path():
                self._config_paths = [config_paths]
            case abc.Sequence() as seq if len(seq) == 0:
                raise ValueError("At least one config path is required.")
            case abc.Sequence():
                self._config_paths = [
                    (
                        config_path
                        if isinstance(config_path, pathlib.Path)
                        else pathlib.Path(config_path)
                    )
                    for config_path in config_paths
                ]
            case unexpected:
                assert_never(unexpected)
        self._output: Sender[abc.Mapping[str, Any]] = output
        self._force_polling: bool = force_polling
        self._polling_interval: timedelta = polling_interval

    def _read_config(self) -> abc.Mapping[str, Any] | None:
        """Read the contents of the configuration file.

        Returns:
            A dictionary containing configuration variables.
        """
        error_count = 0
        config: dict[str, Any] = {}

        for config_path in self._config_paths:
            _logger.info(
                "[%s] Reading configuration file %r...", self.name, str(config_path)
            )
            try:
                with config_path.open("rb") as toml_file:
                    data = tomllib.load(toml_file)
                    _logger.info(
                        "[%s] Configuration file %r read successfully.",
                        self.name,
                        str(config_path),
                    )
                    config = _recursive_update(config, data)
            except ValueError as err:
                _logger.error("[%s] Can't read config file, err: %s", self.name, err)
                error_count += 1
            except OSError as err:
                # It is ok for config file to don't exist.
                _logger.error(
                    "[%s] Error reading config file %r (%s). Ignoring it.",
                    self.name,
                    str(config_path),
                    err,
                )
                error_count += 1

        if error_count == len(self._config_paths):
            _logger.error(
                "[%s] Can't read any of the config files, ignoring config update.", self
            )
            return None

        _logger.info(
            "[%s] Read %s/%s configuration files successfully.",
            self.name,
            len(self._config_paths) - error_count,
            len(self._config_paths),
        )
        return config

    async def send_config(self) -> None:
        """Send the configuration to the output sender."""
        config = self._read_config()
        if config is not None:
            await self._output.send(config)

    async def _run(self) -> None:
        """Monitor for and send configuration file updates.

        At startup, the Config Manager sends the current config so that it
        can be cached in the Broadcast channel and served to receivers even if
        there hasn't been any change to the config file itself.
        """
        await self.send_config()

        parent_paths = {p.parent for p in self._config_paths}

        # FileWatcher can't watch for non-existing files, so we need to watch for the
        # parent directories instead just in case a configuration file doesn't exist yet
        # or it is deleted and recreated again.
        file_watcher = FileWatcher(
            paths=list(parent_paths),
            event_types={EventType.CREATE, EventType.MODIFY},
            force_polling=self._force_polling,
            polling_interval=self._polling_interval,
        )

        try:
            async for event in file_watcher:
                if not event.path.exists():
                    _logger.error(
                        "[%s] Received event %s, but the watched path %s doesn't exist.",
                        self.name,
                        event,
                        event.path,
                    )
                    continue
                # Since we are watching the whole parent directories, we need to make
                # sure we only react to events related to the configuration files we
                # are interested in.
                #
                # pathlib.Path.samefile raises error if any path doesn't exist so we need to
                # make sure the paths exists before calling it. This could happen as it is not
                # required that all config files exist, only one is required but we don't know
                # which.
                if not any(
                    event.path.samefile(p) for p in self._config_paths if p.exists()
                ):
                    continue

                match event.type:
                    case EventType.CREATE:
                        _logger.info(
                            "[%s] The configuration file %s was created, sending new config...",
                            self.name,
                            event.path,
                        )
                        await self.send_config()
                    case EventType.MODIFY:
                        _logger.info(
                            "[%s] The configuration file %s was modified, sending update...",
                            self.name,
                            event.path,
                        )
                        await self.send_config()
                    case EventType.DELETE:
                        _logger.error(
                            "[%s] Unexpected DELETE event for path %s. Please report this "
                            "issue to Frequenz.",
                            self.name,
                            event.path,
                        )
                    case _:
                        assert_never(event.type)
        finally:
            del file_watcher


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
