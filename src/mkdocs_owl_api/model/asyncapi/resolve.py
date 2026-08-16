from __future__ import annotations

from dataclasses import replace

from ..doc_types import Reference
from .types import (
    AsyncApiDoc,
    SecurityEntry,
    SecurityRequirement,
    SecurityScheme,
)


class SecurityIterator:
    """
    A `security` list as resolved SecuritySchema.
    """

    __slots__ = ("_entries", "_doc", "_index")

    def __init__(self, entries: tuple[SecurityEntry, ...], doc: AsyncApiDoc) -> None:
        self._entries = entries
        self._doc = doc
        self._index = 0

    def __iter__(self) -> SecurityIterator:
        return self

    def __next__(self) -> SecurityScheme:
        if self._index >= len(self._entries):
            raise StopIteration
        entry = self._entries[self._index]
        self._index += 1
        return self._scheme(entry)

    def _scheme(self, entry: SecurityEntry) -> SecurityScheme:
        if isinstance(entry, SecurityScheme):
            return entry
        if isinstance(entry, Reference):
            return self._doc.security_scheme(entry) or SecurityScheme(name=entry.name)
        return self._requirement_as_scheme(entry)

    def _requirement_as_scheme(self, entry: SecurityRequirement) -> SecurityScheme:
        declared = self._doc.security_scheme_named(entry.scheme_name)
        if declared is None:
            return SecurityScheme(name=entry.scheme_name, scopes=entry.scopes)
        return replace(declared, scopes=entry.scopes)
