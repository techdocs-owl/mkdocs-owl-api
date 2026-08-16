"""
Readers shared by both AsyncAPI dialects.

Nothing here asks which version it is reading. Where the two genuinely
restructure - servers, channels, operations, components - the `Dialect` decides;
where they merely use keys the other never emits, the key's presence is the
answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ...doc_parser import read_external_docs, read_tag
from ...parse_refs import RefResolver
from ...parse_report import Reporter
from ...parse_util import (
    extensions_of,
    is_mapping,
    kind_of,
    read_mapping,
    read_str,
    read_str_map,
    read_str_tuple,
)
from ...jsonschema.schema_parser import read_schema
from ..types import (
    CorrelationId,
    Message,
    MessageExample,
    Parameter,
    SecurityScheme,
    SecuritySchemeType,
    ServerVariable,
)


def name_of(pointer: str) -> str:
    """The component name a pointer ends in."""
    return pointer.rsplit("/", 1)[-1]


def read_bindings(raw: Mapping[str, Any], report: Reporter) -> dict[str, Any]:
    """
    Protocol bindings, kept verbatim.

    A binding's shape is defined by its protocol, not by AsyncAPI, so there is
    nothing here to model - only something to carry.
    """
    node = read_mapping(raw, "bindings", report)
    return dict(node) if node else {}


def read_tags(raw: Any, report: Reporter) -> tuple:
    if not isinstance(raw, list):
        if raw is not None:
            report.warn(f"expected an array, found {kind_of(raw)}")
        return ()
    tags = [read_tag(item, report.at(index)) for index, item in enumerate(raw)]
    return tuple(tag for tag in tags if tag is not None)


def read_server_variable(raw: Any, report: Reporter) -> ServerVariable:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return ServerVariable()
    return ServerVariable(
        default=read_str(raw, "default", report) or "",
        enum=read_str_tuple(raw, "enum", report),
        description=read_str(raw, "description", report),
        examples=read_str_tuple(raw, "examples", report),
    )


def read_server_variables(
    raw: Mapping[str, Any], resolver: RefResolver, report: Reporter,
) -> dict[str, ServerVariable]:
    node = read_mapping(raw, "variables", report)
    if node is None:
        return {}
    return {
        str(name): read_server_variable(
            resolver.resolve(value, report.at("variables", name)),
            report.at("variables", name),
        )
        for name, value in node.items()
    }


def read_correlation_id(
    raw: Any, resolver: RefResolver, report: Reporter,
) -> CorrelationId | None:
    raw = resolver.resolve(raw, report)
    if raw is None:
        return None
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    return CorrelationId(
        location=read_str(raw, "location", report) or "",
        description=read_str(raw, "description", report),
    )


def read_examples(raw: Mapping[str, Any], report: Reporter) -> tuple[MessageExample, ...]:
    entries = raw.get("examples")
    if entries is None:
        return ()
    if not isinstance(entries, list):
        report.at("examples").warn(f"expected an array, found {kind_of(entries)}")
        return ()

    examples: list[MessageExample] = []
    for index, entry in enumerate(entries):
        if is_mapping(entry):
            examples.append(MessageExample(
                name=read_str(entry, "name", report.at("examples", index)),
                summary=read_str(entry, "summary", report.at("examples", index)),
                headers=entry.get("headers"),
                payload=entry.get("payload"),
            ))
        else:
            # 2.x also allows a bare payload where an example object is expected.
            examples.append(MessageExample(payload=entry))
    return tuple(examples)


def apply_traits(
    raw: Mapping[str, Any], resolver: RefResolver, report: Reporter,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """
    Fold a trait list into the object it applies to.

    The spec says a trait's fields are merged in and the object's own fields
    win, so the merge happens on the raw description before anything is read -
    one reader then sees one object. The names are kept so what was applied can
    still be said.
    """
    merged: dict[str, Any] = {}
    names: list[str] = []

    for index, entry in enumerate(raw.get("traits") or []):
        at = report.at("traits", index)
        if is_mapping(entry) and isinstance(entry.get("$ref"), str):
            names.append(name_of(entry["$ref"]))
        trait = resolver.resolve(entry, at)
        if is_mapping(trait):
            merged.update({k: v for k, v in trait.items() if k != "traits"})
        elif trait is not None:
            at.warn(f"expected an object, found {kind_of(trait)}")

    merged.update({k: v for k, v in raw.items() if k != "traits"})
    return merged, tuple(names)


def read_message(
    name: str, raw: Any, resolver: RefResolver, report: Reporter,
) -> Message | None:
    raw = resolver.resolve(raw, report)
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None

    merged, trait_names = apply_traits(raw, resolver, report)
    headers = merged.get("headers")
    payload = merged.get("payload")

    return Message(
        name=read_str(merged, "name", report) or name,
        message_id=read_str(merged, "messageId", report),
        title=read_str(merged, "title", report),
        summary=read_str(merged, "summary", report),
        description=read_str(merged, "description", report),
        content_type=read_str(merged, "contentType", report),
        headers=read_schema(headers, report.at("headers")) if headers is not None else None,
        payload=read_schema(payload, report.at("payload")) if payload is not None else None,
        correlation_id=read_correlation_id(
            merged.get("correlationId"), resolver, report.at("correlationId"),
        ),
        tags=read_tags(merged.get("tags"), report.at("tags")),
        external_docs=read_external_docs(
            merged.get("externalDocs"), report.at("externalDocs"),
        ),
        examples=read_examples(merged, report),
        bindings=read_bindings(merged, report),
        trait_names=trait_names,
        extensions=extensions_of(merged),
    )


#: Schema keywords a parameter may state directly rather than under a `schema`.
_INLINE_PARAMETER_KEYS = ("enum", "default", "examples")


def read_parameter(name: str, raw: Any, resolver: RefResolver, report: Reporter) -> Parameter:
    """
    A channel parameter.

    One dialect nests the value's shape in a `schema` and the other states
    `enum`, `default` and `examples` on the parameter; both land on one schema.
    A parameter substituted into an address is a string, so that is the type
    where the source names none.
    """
    raw = resolver.resolve(raw, report)
    if not is_mapping(raw):
        if raw is not None:
            report.warn(f"expected an object, found {kind_of(raw)}")
        return Parameter(name=name)

    declared = raw.get("schema")
    source = dict(declared) if is_mapping(declared) else {}
    source.update({k: raw[k] for k in _INLINE_PARAMETER_KEYS if k in raw})

    schema = read_schema(source, report.at("schema") if declared else report)
    if schema is not None and not schema.types:
        schema = replace(schema, types=("string",))

    return Parameter(
        name=name,
        description=read_str(raw, "description", report),
        location=read_str(raw, "location", report),
        schema=schema,
    )


def read_parameters(
    raw: Mapping[str, Any], resolver: RefResolver, report: Reporter,
) -> dict[str, Parameter]:
    node = read_mapping(raw, "parameters", report)
    if node is None:
        return {}
    return {
        str(name): read_parameter(str(name), value, resolver, report.at("parameters", name))
        for name, value in node.items()
    }


def read_security_entries(raw: Any, report: Reporter) -> list[Any]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        report.warn(f"expected an array, found {kind_of(raw)}")
        return []
    return raw


def read_security_scheme(
    name: str, raw: Any, report: Reporter,
) -> SecurityScheme | None:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    declared = read_str(raw, "type", report)
    try:
        scheme_type = SecuritySchemeType(declared)
    except ValueError:
        report.warn(f"unknown security scheme type `{declared}`")
        return None

    flows = read_mapping(raw, "flows", report) or {}
    available: dict[str, str] = {}
    for flow_name, flow in flows.items():
        if is_mapping(flow):
            available.update(read_str_map(flow, "availableScopes", report.at("flows", flow_name))
                             or read_str_map(flow, "scopes", report.at("flows", flow_name)))

    return SecurityScheme(
        name=name,
        type=scheme_type,
        description=read_str(raw, "description", report),
        parameter_name=read_str(raw, "name", report),
        location=read_str(raw, "in", report),
        scheme=read_str(raw, "scheme", report),
        bearer_format=read_str(raw, "bearerFormat", report),
        open_id_connect_url=read_str(raw, "openIdConnectUrl", report),
        scopes=read_str_tuple(raw, "scopes", report),
        available_scopes=available,
        extensions=extensions_of(raw),
    )
