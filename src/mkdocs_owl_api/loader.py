"""
Read AsyncAPI/OpenAPI/JSON Schema specs. Reload and inline `$ref`s.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

import fsspec
import yaml


class SpecError(Exception):
    """The spec could not be fetched, read or parsed."""


def _parse(text: str) -> Any:
    """
    Spec text as data in JSON or YAML.
    """
    try:
        return json.loads(text)
    except ValueError:
        return yaml.safe_load(text)


def _pointer(doc: Any, fragment: str) -> Any:
    """
    Value at an RFC 6901 JSON pointer, or None where the pointer does not resolve.
    """
    for token in unquote(fragment).lstrip("/").split("/") if fragment else []:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(doc, dict):
            if token not in doc:
                return None
            doc = doc[token]
        elif isinstance(doc, list) and token.isdigit() and int(token) < len(doc):
            doc = doc[int(token)]
        else:
            return None
    return doc


class FileReader:
    """
    Reads a location as text or bytes.
    """

    def __init__(self, base: Path | str = ".") -> None:
        self._base = Path(base)

    def uri(self, location: str) -> str:
        """
        Absolute URI for `location`, resolving a relative path against `base`.
        """
        if len(urlsplit(location).scheme) > 1:
            return location
        return (self._base / location).resolve().as_uri()

    def read_text(self, location: str, encoding: str = "utf-8") -> str:
        with fsspec.open(urldefrag(self.uri(location)).url, "rt", encoding=encoding) as handle:
            return handle.read()

    def read_bytes(self, location: str) -> bytes:
        with fsspec.open(urldefrag(self.uri(location)).url, "rb") as handle:
            return handle.read()


class SpecReader:
    """
    Reads a spec document as data and inlines its external `$ref`s.
    """

    def __init__(self, base: Path | str = ".", reader: FileReader | None = None) -> None:
        self._reader = reader or FileReader(base)
        self._cache: dict[str, Any] = {}

    def read(self, location: str) -> dict[str, Any]:
        """
        Reads the spec at `location`, with external refs inlined.
        """
        uri = self._reader.uri(location)
        try:
            text = self._reader.read_text(uri)
        except FileNotFoundError as exc:
            raise SpecError(f"spec file not found: `{uri}`") from exc
        except Exception as exc:
            raise SpecError(f"spec read error: `{uri}`: {exc}") from exc

        try:
            spec = _parse(text)
        except yaml.YAMLError as exc:
            raise SpecError(f"spec parse error: `{uri}`: {exc}") from exc

        if spec is None:
            raise SpecError(f"spec file is empty: `{uri}` contains no content.")
        if not isinstance(spec, dict):
            raise SpecError(f"unexpected spec content: `{uri}` did not parse to a mapping.")

        self._cache[urldefrag(uri).url] = spec
        self._inline(spec, uri, frozenset())
        return spec

    def _document(self, uri: str) -> Any:
        """The parsed document at `uri`, or None if it cannot be read."""
        if uri not in self._cache:
            try:
                self._cache[uri] = _parse(self._reader.read_text(uri))
            except Exception:
                self._cache[uri] = None
        return self._cache[uri]

    def _inline(self, node: Any, base_uri: str, seen: frozenset[str]) -> None:
        """Replace every external `$ref` at or below `node`, in place."""
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and not ref.startswith("#"):
                self._expand(node, urljoin(base_uri, ref), seen)
                return
            for value in node.values():
                self._inline(value, base_uri, seen)
        elif isinstance(node, list):
            for item in node:
                self._inline(item, base_uri, seen)

    def _expand(self, node: dict[str, Any], target: str, seen: frozenset[str]) -> None:
        """
        Splice the document at `target` into `node`.
        """
        if target in seen:
            return
        doc_uri, fragment = urldefrag(target)
        resolved = _pointer(self._document(doc_uri), fragment)
        if not isinstance(resolved, dict):
            return

        node.pop("$ref")
        for key, value in copy.deepcopy(resolved).items():
            node.setdefault(key, value)
        self._inline(node, doc_uri, seen | {target})
