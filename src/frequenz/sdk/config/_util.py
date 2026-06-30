# License: MIT
# Copyright © 2024 Frequenz Energy-as-a-Service GmbH

"""Utilities to deal with configuration."""

from collections.abc import Mapping
from typing import Any, ClassVar, Protocol, TypeVar, cast

import marshmallow
from marshmallow import Schema
from marshmallow_dataclass import class_schema

from ._base_schema import BaseConfigSchema


# This is a hack that relies on identifying dataclasses by looking into an undocumented
# property of dataclasses[1], so it might break in the future. Nevertheless, it seems to
# be widely used in the community, for example `mypy` and `pyright` seem to rely on
# it[2].
#
# [1]: https://github.com/python/mypy/issues/15974#issuecomment-1694781006
# [2]: https://github.com/python/mypy/issues/15974#issuecomment-1694993493
class Dataclass(Protocol):
    """A protocol for dataclasses."""

    __dataclass_fields__: ClassVar[dict[str, Any]]
    """The fields of the dataclass."""


DataclassT = TypeVar("DataclassT", bound=Dataclass)
"""Type variable for configuration classes."""


def load_config(
    cls: type[DataclassT],
    config: Mapping[str, Any],
    /,
    *,
    base_schema: type[Schema] | None = BaseConfigSchema,
    marshmallow_load_kwargs: dict[str, Any] | None = None,
) -> DataclassT:
    """Load a configuration from a dictionary into an instance of a configuration class.

    The configuration class is expected to be a [`dataclasses.dataclass`][], which is
    used to create a [`marshmallow.Schema`][] schema to validate the configuration
    dictionary using [`marshmallow_dataclass.class_schema`][] (which in turn uses the
    [`marshmallow.Schema.load`][] method to do the validation and deserialization).

    To customize the schema derived from the configuration dataclass, you can use the
    `metadata` key in [`dataclasses.field`][] to pass extra options to
    [`marshmallow_dataclass`][] to be used during validation and deserialization.

    Additional arguments can be passed to [`marshmallow.Schema.load`][] using keyword
    arguments `marshmallow_load_kwargs`.

    Note:
        This method will raise [`marshmallow.ValidationError`][] if the configuration
        dictionary is invalid and you have to have in mind all of the gotchas of
        [`marshmallow`][] and [`marshmallow_dataclass`][] apply when using this
        function.  It is recommended to carefully read the documentation of these
        libraries.

    Args:
        cls: The configuration class.
        config: The configuration dictionary.
        base_schema: An optional class to be used as a base schema for the configuration
            class. This allow using custom fields for example. Will be passed to
            [`marshmallow_dataclass.class_schema`][].
        marshmallow_load_kwargs: Additional arguments to be passed to
            [`marshmallow.Schema.load`][].

    Returns:
        The loaded configuration as an instance of the configuration class.
    """
    _validate_load_kwargs(marshmallow_load_kwargs)

    instance = class_schema(cls, base_schema)().load(
        config, **(marshmallow_load_kwargs or {})
    )
    # We need to cast because `.load()` comes from marshmallow and doesn't know which
    # type is returned.
    return cast(DataclassT, instance)


def _validate_load_kwargs(marshmallow_load_kwargs: dict[str, Any] | None) -> None:
    """Validate the marshmallow load kwargs.

    This function validates the `unknown` option of the marshmallow load kwargs to
    prevent loading unknown fields when loading to a dataclass.

    Args:
        marshmallow_load_kwargs: The dictionary to get the marshmallow load kwargs from.

    Raises:
        ValueError: If the `unknown` option is set to [`marshmallow.INCLUDE`][].
    """
    if (
        marshmallow_load_kwargs
        and marshmallow_load_kwargs.get("unknown") == marshmallow.INCLUDE
    ):
        raise ValueError(
            "The 'unknown' option can't be 'INCLUDE' when loading to a dataclass"
        )
