"""
Readers for document metadata: `info` and its neighbours.

Spelled identically by every flavour and version this plugin reads, so nothing
here takes a dialect. A few fields - `info.summary`, `license.identifier` -
exist only in newer versions, and reading a key that is not there costs
nothing.

Each reader takes the value it is to read plus a reporter already positioned at
that value.
"""

from __future__ import annotations

from typing import Any

from .doc_model import Contact, ExternalDocs, Info, License, Tag
from .parse_report import Reporter
from .parse_util import extensions_of, is_mapping, kind_of, read_str


def read_contact(raw: Any, report: Reporter) -> Contact | None:
    if raw is None:
        return None
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    contact = Contact(
        name=read_str(raw, "name", report),
        url=read_str(raw, "url", report),
        email=read_str(raw, "email", report),
    )
    return contact if contact != Contact() else None


def read_license(raw: Any, report: Reporter) -> License | None:
    if raw is None:
        return None
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    license_ = License(
        name=read_str(raw, "name", report),
        identifier=read_str(raw, "identifier", report),
        url=read_str(raw, "url", report),
    )
    return license_ if license_ != License() else None


def read_external_docs(raw: Any, report: Reporter) -> ExternalDocs | None:
    if raw is None:
        return None
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    url = read_str(raw, "url", report)
    description = read_str(raw, "description", report)
    if url is None and description is None:
        return None
    if url is None:
        report.warn("no `url`, so the link cannot be followed")
    return ExternalDocs(url=url or "", description=description)


def read_info(raw: Any, report: Reporter) -> Info:
    """
    Always returns an `Info`. A missing or unusable one becomes an empty record
    plus a warning, so the rest of the document is still read.
    """
    if raw is None:
        report.warn("missing `info`")
        return Info()
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return Info()

    title = read_str(raw, "title", report)
    version = read_str(raw, "version", report)
    if title is None:
        report.warn("missing `title`")
    if version is None:
        report.warn("missing `version`")

    return Info(
        title=title or "",
        version=version or "",
        summary=read_str(raw, "summary", report),
        description=read_str(raw, "description", report),
        terms_of_service=read_str(raw, "termsOfService", report),
        contact=read_contact(raw.get("contact"), report.at("contact")),
        license=read_license(raw.get("license"), report.at("license")),
        extensions=extensions_of(raw),
    )


def read_tag(raw: Any, report: Reporter) -> Tag | None:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    name = read_str(raw, "name", report)
    if not name:
        report.warn("no `name`, so nothing can reference it")
        return None
    return Tag(
        name=name,
        description=read_str(raw, "description", report),
        external_docs=read_external_docs(
            raw.get("externalDocs"), report.at("externalDocs"),
        ),
        extensions=extensions_of(raw),
    )


def read_tags(raw: Any, report: Reporter) -> tuple[Tag, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        report.warn(f"expected an array, found {kind_of(raw)}")
        return ()
    tags = [read_tag(item, report.at(index)) for index, item in enumerate(raw)]
    return tuple(tag for tag in tags if tag is not None)


__all__ = [
    "read_contact",
    "read_external_docs",
    "read_info",
    "read_license",
    "read_tag",
    "read_tags",
]
