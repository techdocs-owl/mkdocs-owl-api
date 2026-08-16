"""
Parser for a JsonSchema document.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..doc_types import Info
from ..parse_report import ParseResult, Reporter
from ..parse_util import is_mapping, kind_of, read_mapping, read_str
from .schema_parser import read_schema
from .schema_types import Schema
from .types import JsonSchemaDialect, JsonSchemaDoc

__all__ = ["parse_document"]

_DIALECTS = {
    "draft-04": JsonSchemaDialect.DRAFT_04,
    "draft-06": JsonSchemaDialect.DRAFT_06,
    "draft-07": JsonSchemaDialect.DRAFT_07,
    "2019-09": JsonSchemaDialect.DRAFT_2019_09,
    "2020-12": JsonSchemaDialect.DRAFT_2020_12,
}

_FALLBACK = JsonSchemaDialect.DRAFT_2020_12


def _detect(raw: Mapping[str, Any], report: Reporter) -> tuple[JsonSchemaDialect, str]:
    """
    Detect the dialect from the `$schema` URI.
    Undetected falls back to the newest dialect.
    """
    declared = read_str(raw, "$schema", report)
    if declared is None:
        report.warn("no `$schema`, reading the document as 2020-12")
        return _FALLBACK, ""

    for marker, dialect in _DIALECTS.items():
        if marker in declared:
            return dialect, declared

    report.warn(f"unknown `$schema` `{declared}`, reading the document as 2020-12")
    return _FALLBACK, declared


def _read_definitions(
    raw: Mapping[str, Any], report: Reporter,
) -> dict[str, Schema]:
    """
    Key `definitions` for draft-04 through draft-07, `$defs` is 2019-09 onward.
    """
    definitions: dict[str, Schema] = {}
    for key in ("definitions", "$defs"):
        node = read_mapping(raw, key, report)
        if node is None:
            continue
        for name, value in node.items():
            schema = read_schema(value, report.at(key, name))
            if schema is not None:
                definitions[str(name)] = schema
    return definitions


def _info(root: Schema) -> Info:
    return Info(title=root.title or "", description=root.description)


def parse_document(raw: Any) -> ParseResult:
    """
    `$schema`, `$id`, `$defs` ( or`definitions`) persisted in JsonSchemaDoc,
    everything else goes to root Schema.
    """
    report = Reporter()
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return ParseResult(JsonSchemaDoc(), report.warnings)

    dialect, spec_version = _detect(raw, report)
    root = read_schema(raw, report) or Schema()

    doc = JsonSchemaDoc(
        dialect=dialect,
        spec_version=spec_version,
        schema_id=read_str(raw, "$id", report) or read_str(raw, "id", report),
        info=_info(root),
        root=root,
        definitions=_read_definitions(raw, report),
        external_docs=root.external_docs,
        extensions=dict(root.extensions),
    )
    return ParseResult(doc, report.warnings)
