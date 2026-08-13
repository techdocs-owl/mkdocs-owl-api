"""
Entry point: a raw OpenAPI document in, an `OpenApiDoc` out.

Which dialect wrote it is decided once, here, and never asked again.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...common.doc_parser import read_external_docs, read_info, read_tags
from ...common.parse_report import ParseResult, Reporter
from ...common.parse_util import extensions_of, is_mapping, kind_of, read_str
from ..model import OpenApiDialect, OpenApiDoc
from .dialect import Dialect, OpenApi3Dialect, Swagger2Dialect
from .document import read_paths
from ...common.parse_refs import RefResolver
from .security import read_requirements

__all__ = ["parse_document"]


def _detect(raw: Mapping[str, Any], report: Reporter) -> tuple[OpenApiDialect, str]:
    """
    The dialect, from whichever root key states it.

    An unrecognised version is read as the closest one that is known rather than
    refused: the caller already established that this document is OpenAPI, and
    reading most of it beats reading none of it.
    """
    version = read_str(raw, "openapi", report)
    if version is not None:
        if version.startswith("3.1"):
            return OpenApiDialect.V3_1, version
        if version.startswith("3.0"):
            return OpenApiDialect.V3_0, version
        report.warn(f"unknown OpenAPI version `{version}`, reading it as 3.1")
        return OpenApiDialect.V3_1, version

    version = read_str(raw, "swagger", report)
    if version is not None:
        if not version.startswith("2.0"):
            report.warn(f"unknown Swagger version `{version}`, reading it as 2.0")
        return OpenApiDialect.V2_0, version

    report.warn("no `openapi` or `swagger` version, reading the document as 3.1")
    return OpenApiDialect.V3_1, ""


def parse_document(raw: Any) -> ParseResult:
    """
    Read a document.

    Never raises: content that cannot be used is dropped and reported, so a
    single malformed operation costs one section rather than the whole page.
    """
    report = Reporter()
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return ParseResult(OpenApiDoc(), report.warnings)

    dialect_version, spec_version = _detect(raw, report)
    resolver = RefResolver(raw)
    dialect: Dialect = (
        Swagger2Dialect(raw, resolver)
        if dialect_version is OpenApiDialect.V2_0
        else OpenApi3Dialect(raw, resolver, dialect_version)
    )

    doc = OpenApiDoc(
        dialect=dialect_version,
        spec_version=spec_version,
        info=read_info(raw.get("info"), report.at("info")),
        servers=dialect.servers(report),
        tags=read_tags(raw.get("tags"), report.at("tags")),
        paths=read_paths(raw.get("paths"), dialect, resolver, report.at("paths")),
        components=dialect.components(report),
        security=(
            read_requirements(raw["security"], report.at("security"))
            if "security" in raw else ()
        ),
        external_docs=read_external_docs(
            raw.get("externalDocs"), report.at("externalDocs"),
        ),
        extensions=extensions_of(raw),
    )
    return ParseResult(doc, report.warnings)
