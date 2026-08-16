"""
Local `$ref` resolution for the objects that are not schemas.

Inside a schema, `$ref` is a JSON Schema keyword that applies in place, so
`Schema.ref` records it and nothing is followed. Elsewhere a reference stands
*for* another object rather than describing one - a parameter is not "a
reference to a parameter", it is that parameter. Those are followed here and
their target read in place.

External references are already inlined by the loader, so only local pointers
reach this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .parse_report import Reporter
from .parse_util import is_mapping


def _unescape(token: str) -> str:
    """RFC 6901 unescaping. `~1` before `~0`, or `~01` decodes wrongly."""
    return token.replace("~1", "/").replace("~0", "~")


class RefResolver:
    """
    Follows local pointers against the raw document.

    Resolution happens before reading, so a referenced object is parsed exactly
    as if it had been written in place.
    """

    __slots__ = ("_root",)

    def __init__(self, root: Mapping[str, Any]):
        self._root = root

    def lookup(self, pointer: str, report: Reporter) -> Any | None:
        if pointer == "#":
            return self._root
        if not pointer.startswith("#/"):
            report.warn(f"cannot follow non-local reference `{pointer}`")
            return None

        node: Any = self._root
        for token in pointer[2:].split("/"):
            key = _unescape(token)
            if is_mapping(node) and key in node:
                node = node[key]
                continue
            if isinstance(node, list):
                try:
                    node = node[int(key)]
                    continue
                except (ValueError, IndexError):
                    pass
            report.warn(f"reference `{pointer}` does not resolve")
            return None
        return node

    def resolve(self, node: Any, report: Reporter) -> Any:
        """
        Follow `$ref` chains until something that is not a reference.

        A cycle among non-schema objects is malformed rather than merely
        recursive, so it warns and yields nothing.
        """
        seen: set[str] = set()
        while is_mapping(node) and isinstance(node.get("$ref"), str):
            pointer = node["$ref"]
            if pointer in seen:
                report.warn(f"reference `{pointer}` is circular")
                return None
            seen.add(pointer)
            node = self.lookup(pointer, report)
            if node is None:
                return None
        return node
