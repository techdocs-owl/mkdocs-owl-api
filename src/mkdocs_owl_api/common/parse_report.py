"""
Warning collection for spec parsing.

Parsing never raises for bad content inside an otherwise loadable document: it
records what it could not use and carries on, so one malformed operation cannot
blank a whole page. Only a document that is not a spec at all is fatal, and that
check lives in the loader.
"""

from __future__ import annotations

from dataclasses import dataclass

from .doc_model import ApiDoc


def _escape(segment: str) -> str:
    """JSON Pointer escaping, per RFC 6901."""
    return segment.replace("~", "~0").replace("/", "~1")


@dataclass(frozen=True)
class ParseWarning:
    """Something in the source that could not be used, and where it was."""

    pointer: str
    message: str

    def __str__(self) -> str:
        return f"{self.pointer}: {self.message}"


class Reporter:
    """
    Collects warnings, tracking where in the document they came from.

    `at()` returns a child positioned one level deeper that shares the parent's
    collection, so a reader can be handed a reporter already pointing at the
    node it is about to read and never has to know its own path.
    """

    __slots__ = ("_pointer", "_sink")

    def __init__(self, pointer: str = "#", _sink: list[ParseWarning] | None = None):
        self._pointer = pointer
        self._sink: list[ParseWarning] = [] if _sink is None else _sink

    def at(self, *segments: object) -> Reporter:
        pointer = self._pointer
        for segment in segments:
            pointer = f"{pointer}/{_escape(str(segment))}"
        return Reporter(pointer, self._sink)

    def warn(self, message: str) -> None:
        self._sink.append(ParseWarning(self._pointer, message))

    @property
    def pointer(self) -> str:
        return self._pointer

    @property
    def warnings(self) -> tuple[ParseWarning, ...]:
        return tuple(self._sink)


@dataclass(frozen=True)
class ParseResult:
    """
    A parsed document and everything that could not be used along the way.
    """

    doc: ApiDoc
    warnings: tuple[ParseWarning, ...] = ()
