"""
Typed reads off a raw spec mapping.

Every reader follows one contract: a key that is absent yields `None` silently,
and a key that is present with the wrong type yields `None` *and* a warning.
That is the whole of the "keep everything I can find" policy - a value is
dropped only when it cannot be used, and never quietly.

Keywords that are simply not modelled are not this module's business: callers
never ask for them, so nothing warns about them.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any


def kind_of(value: Any) -> str:
    """A readable name for a value's type, for use in warnings."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, Mapping):
        return "an object"
    if isinstance(value, Sequence):
        return "an array"
    return type(value).__name__


def is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def read_str(raw: Mapping[str, Any], key: str, report) -> str | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, str):
        return value
    report.at(key).warn(f"expected a string, found {kind_of(value)}")
    return None


def read_bool(raw: Mapping[str, Any], key: str, report) -> bool | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, bool):
        return value
    report.at(key).warn(f"expected a boolean, found {kind_of(value)}")
    return None


def read_int(raw: Mapping[str, Any], key: str, report) -> int | None:
    if key not in raw:
        return None
    value = raw[key]
    # `bool` is a subclass of `int`, and `true` is not a count.
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    report.at(key).warn(f"expected an integer, found {kind_of(value)}")
    return None


def read_number(raw: Mapping[str, Any], key: str, report) -> float | int | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    report.at(key).warn(f"expected a number, found {kind_of(value)}")
    return None


def read_list(raw: Mapping[str, Any], key: str, report) -> list[Any] | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    report.at(key).warn(f"expected an array, found {kind_of(value)}")
    return None


def read_mapping(raw: Mapping[str, Any], key: str, report) -> Mapping[str, Any] | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, Mapping):
        return value
    report.at(key).warn(f"expected an object, found {kind_of(value)}")
    return None


def read_str_tuple(raw: Mapping[str, Any], key: str, report) -> tuple[str, ...]:
    """
    A list of strings, skipping - and reporting - members that are not strings.
    """
    items = read_list(raw, key, report)
    if items is None:
        return ()
    kept: list[str] = []
    for index, item in enumerate(items):
        if isinstance(item, str):
            kept.append(item)
        else:
            report.at(key, index).warn(f"expected a string, found {kind_of(item)}")
    return tuple(kept)


def read_str_map(raw: Mapping[str, Any], key: str, report) -> dict[str, str]:
    """A string-to-string map, skipping - and reporting - non-string values."""
    node = read_mapping(raw, key, report)
    if node is None:
        return {}
    kept: dict[str, str] = {}
    for name, value in node.items():
        if isinstance(value, str):
            kept[str(name)] = value
        else:
            report.at(key, name).warn(f"expected a string, found {kind_of(value)}")
    return kept


def extensions_of(
    raw: Mapping[str, Any], consumed: Collection[str] = (),
) -> dict[str, Any]:
    """
    Vendor extensions, kept verbatim.

    `consumed` names extensions already promoted to a modelled field -
    `x-nullable` becomes `Schema.nullable` - which are therefore no longer
    extras. Keeping them here as well would record the same fact twice and make
    two documents that differ only in dialect compare unequal.
    """
    return {
        str(key): value
        for key, value in raw.items()
        if isinstance(key, str) and key.startswith("x-") and key not in consumed
    }
