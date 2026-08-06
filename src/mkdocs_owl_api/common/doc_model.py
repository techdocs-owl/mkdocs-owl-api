"""
Document metadata common to every spec flavour.

Knows nothing about schemas, paths or channels, so both `schema_model` and the
flavour models can import it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Contact:
    """`info.contact`."""

    name: str | None = None
    url: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class License:
    """`info.license`. `identifier` is an SPDX expression."""

    name: str | None = None
    identifier: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class ExternalDocs:
    """A link off the page, wherever `externalDocs` hangs."""

    url: str = ""
    description: str | None = None


@dataclass(frozen=True)
class Info:
    """`info`. `description` keeps its source Markdown verbatim."""

    title: str = ""
    version: str = ""
    summary: str | None = None
    description: str | None = None
    terms_of_service: str | None = None
    contact: Contact | None = None
    license: License | None = None
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Tag:
    """
    A declared tag.

    Operations reference tags by name, so a name used by an operation without a
    declaration here is normal.
    """

    name: str = ""
    description: str | None = None
    external_docs: ExternalDocs | None = None
    extensions: dict[str, Any] = field(default_factory=dict)
