"""
Entry point: a raw AsyncAPI document in, an `AsyncApiDoc` out.

Which dialect wrote it is decided once, here, and never asked again.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...doc_parser import read_external_docs, read_info, read_tags
from ...parse_refs import RefResolver
from ...parse_report import ParseResult, Reporter
from ...parse_util import extensions_of, is_mapping, kind_of, read_str
from ..types import AsyncApiDialect, AsyncApiDoc
from .dialect import Dialect, V2Dialect, V3Dialect

__all__ = ["parse_document"]


def _detect(raw: Mapping[str, Any], report: Reporter) -> tuple[AsyncApiDialect, str]:
    """
    The dialect, from the version the root states.

    An unrecognised version is read as the closest one that is known rather than
    refused: the caller already established that this document is AsyncAPI, and
    reading most of it beats reading none of it.
    """
    version = read_str(raw, "asyncapi", report)
    if version is None:
        report.warn("no `asyncapi` version, reading the document as 3.0")
        return AsyncApiDialect.V3, ""
    if version.startswith("2."):
        return AsyncApiDialect.V2, version
    if version.startswith("3."):
        return AsyncApiDialect.V3, version
    report.warn(f"unknown AsyncAPI version `{version}`, reading it as 3.0")
    return AsyncApiDialect.V3, version


def parse_document(raw: Any) -> ParseResult:
    """
    Read a document.

    Never raises: content that cannot be used is dropped and reported, so a
    single malformed channel costs one section rather than the whole page.
    """
    report = Reporter()
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return ParseResult(AsyncApiDoc(), report.warnings)

    dialect_version, spec_version = _detect(raw, report)
    resolver = RefResolver(raw)
    dialect: Dialect = (
        V2Dialect(raw, resolver) if dialect_version is AsyncApiDialect.V2
        else V3Dialect(raw, resolver)
    )

    channels = dialect.channels(report)
    doc = AsyncApiDoc(
        spec_version=spec_version,
        info=read_info(raw.get("info"), report.at("info")),
        tags=read_tags(raw.get("tags"), report.at("tags")),
        external_docs=read_external_docs(
            raw.get("externalDocs"), report.at("externalDocs"),
        ),
        extensions=extensions_of(raw),
        dialect=dialect_version,
        default_content_type=read_str(raw, "defaultContentType", report),
        servers=dialect.servers(report),
        channels=channels,
        operations=dialect.operations(channels, report),
        components=dialect.components(report),
    )
    return ParseResult(doc, report.warnings)
