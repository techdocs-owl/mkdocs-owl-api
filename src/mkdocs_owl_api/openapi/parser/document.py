"""
Traversal shared by every dialect.

Nothing here asks which version it is reading. Where the dialects genuinely
restructure, this calls the `Dialect` it was handed; where they merely use keys
the other one never emits - `collectionFormat` against `style`, `servers` on a
path item - the key's presence is the answer and no dispatch is needed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...common.doc_parser import read_external_docs
from ...common.parse_report import Reporter
from ...common.parse_util import (
    extensions_of,
    is_mapping,
    kind_of,
    read_bool,
    read_mapping,
    read_str,
    read_str_tuple,
)
from ...common.schema_model import UNSET
from ..model import (
    Encoding,
    Example,
    Header,
    HttpMethod,
    MediaType,
    Operation,
    Parameter,
    ParameterLocation,
    PathItem,
    Response,
    Server,
    ServerVariable,
)
from .refs import RefResolver
from .security import read_requirements

#: 2.0 parameter locations that describe a body rather than a parameter. The
#: dialect turns them into a `RequestBody`, so the traversal skips them.
_BODY_LOCATIONS = frozenset({"body", "formData"})

#: 2.0's `collectionFormat`, as the 3.x style it corresponds to. `tsv` has no
#: 3.x counterpart and is kept verbatim rather than dropped.
_COLLECTION_FORMATS = {
    "ssv": "spaceDelimited",
    "pipes": "pipeDelimited",
    "tsv": "tsv",
}


def read_server_variable(raw: Any, report: Reporter) -> ServerVariable:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return ServerVariable()
    default = read_str(raw, "default", report)
    if default is None:
        report.warn("no `default`")
    return ServerVariable(
        default=default or "",
        enum=read_str_tuple(raw, "enum", report),
        description=read_str(raw, "description", report),
    )


def read_server(raw: Any, report: Reporter) -> Server | None:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    variables = read_mapping(raw, "variables", report) or {}
    return Server(
        url=read_str(raw, "url", report) or "",
        description=read_str(raw, "description", report),
        variables={
            str(name): read_server_variable(value, report.at("variables", name))
            for name, value in variables.items()
        },
        extensions=extensions_of(raw),
    )


def read_servers(raw: Any, report: Reporter) -> tuple[Server, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        report.warn(f"expected an array, found {kind_of(raw)}")
        return ()
    servers = (read_server(item, report.at(index)) for index, item in enumerate(raw))
    return tuple(server for server in servers if server is not None)


def read_example(raw: Any, report: Reporter) -> Example | None:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    return Example(
        summary=read_str(raw, "summary", report),
        description=read_str(raw, "description", report),
        value=raw["value"] if "value" in raw else UNSET,
        external_value=read_str(raw, "externalValue", report),
    )


def read_examples(
    raw: Mapping[str, Any], resolver: RefResolver, report: Reporter,
) -> dict[str, Example]:
    node = read_mapping(raw, "examples", report)
    if node is None:
        return {}
    examples: dict[str, Example] = {}
    for name, value in node.items():
        at = report.at("examples", name)
        example = read_example(resolver.resolve(value, at), at)
        if example is not None:
            examples[str(name)] = example
    return examples


def read_encoding(
    raw: Any, dialect, resolver: RefResolver, report: Reporter,
) -> Encoding | None:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    return Encoding(
        content_type=read_str(raw, "contentType", report),
        headers=read_headers(raw, dialect, resolver, report),
        style=read_str(raw, "style", report),
        explode=read_bool(raw, "explode", report),
        allow_reserved=bool(read_bool(raw, "allowReserved", report)),
    )


def read_media_type(
    raw: Any, dialect, resolver: RefResolver, report: Reporter,
) -> MediaType:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return MediaType()

    encoding_node = read_mapping(raw, "encoding", report) or {}
    encodings: dict[str, Encoding] = {}
    for name, value in encoding_node.items():
        encoding = read_encoding(value, dialect, resolver, report.at("encoding", name))
        if encoding is not None:
            encodings[str(name)] = encoding

    return MediaType(
        schema=dialect.schema_of(raw, report),
        example=raw["example"] if "example" in raw else UNSET,
        examples=read_examples(raw, resolver, report),
        encoding=encodings,
    )


def read_content(
    raw: Mapping[str, Any], dialect, resolver: RefResolver, report: Reporter,
) -> dict[str, MediaType]:
    """A 3.x `content` map. Absent in 2.0, where the dialect builds one."""
    node = read_mapping(raw, "content", report)
    if node is None:
        return {}
    return {
        str(media_type): read_media_type(
            value, dialect, resolver, report.at("content", media_type),
        )
        for media_type, value in node.items()
    }


def read_header(
    raw: Any, dialect, resolver: RefResolver, report: Reporter,
) -> Header | None:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    style, explode = _read_style(raw, None, report)
    return Header(
        description=read_str(raw, "description", report),
        required=bool(read_bool(raw, "required", report)),
        deprecated=bool(read_bool(raw, "deprecated", report)),
        style=style,
        explode=explode,
        schema=dialect.schema_of(raw, report),
        example=raw["example"] if "example" in raw else UNSET,
        examples=read_examples(raw, resolver, report),
        content=read_content(raw, dialect, resolver, report),
    )


def read_headers(
    raw: Mapping[str, Any], dialect, resolver: RefResolver, report: Reporter,
) -> dict[str, Header]:
    node = read_mapping(raw, "headers", report)
    if node is None:
        return {}
    headers: dict[str, Header] = {}
    for name, value in node.items():
        at = report.at("headers", name)
        header = read_header(resolver.resolve(value, at), dialect, resolver, at)
        if header is not None:
            headers[str(name)] = header
    return headers


def _read_style(
    raw: Mapping[str, Any], location: ParameterLocation | None, report: Reporter,
) -> tuple[str | None, bool | None]:
    """
    Serialisation style, from either spelling.

    `style` is 3.x and `collectionFormat` is 2.0, so whichever is present is the
    one the document meant. `csv` is the default in both, and which 3.x style it
    corresponds to depends on where the parameter sits.
    """
    style = read_str(raw, "style", report)
    explode = read_bool(raw, "explode", report)
    if style is not None or "collectionFormat" not in raw:
        return style, explode

    collection_format = read_str(raw, "collectionFormat", report)
    if collection_format == "multi":
        return "form", True
    if collection_format == "csv":
        query_like = location in (ParameterLocation.QUERY, ParameterLocation.COOKIE)
        return ("form" if query_like else "simple"), explode
    return _COLLECTION_FORMATS.get(collection_format or "", collection_format), explode


def read_parameter(
    raw: Any, dialect, resolver: RefResolver, report: Reporter,
) -> Parameter | None:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None

    name = read_str(raw, "name", report)
    if not name:
        report.warn("no `name`")
        return None

    declared = read_str(raw, "in", report)
    try:
        location = ParameterLocation(declared)
    except ValueError:
        report.at("in").warn(f"unknown location `{declared}`")
        return None

    style, explode = _read_style(raw, location, report)
    return Parameter(
        name=name,
        location=location,
        description=read_str(raw, "description", report),
        required=bool(read_bool(raw, "required", report)),
        deprecated=bool(read_bool(raw, "deprecated", report)),
        allow_empty_value=bool(read_bool(raw, "allowEmptyValue", report)),
        style=style,
        explode=explode,
        schema=dialect.schema_of(raw, report),
        example=raw["example"] if "example" in raw else UNSET,
        examples=read_examples(raw, resolver, report),
        content=read_content(raw, dialect, resolver, report),
        extensions=extensions_of(raw),
    )


def read_parameters(
    raw: Any, dialect, resolver: RefResolver, report: Reporter,
) -> tuple[Parameter, ...]:
    """
    A `parameters` list, minus the 2.0 entries that describe a body.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        report.warn(f"expected an array, found {kind_of(raw)}")
        return ()

    parameters: list[Parameter] = []
    for index, entry in enumerate(raw):
        at = report.at(index)
        resolved = resolver.resolve(entry, at)
        if is_mapping(resolved) and resolved.get("in") in _BODY_LOCATIONS:
            continue
        parameter = read_parameter(resolved, dialect, resolver, at)
        if parameter is not None:
            parameters.append(parameter)
    return tuple(parameters)


def merge_parameters(
    inherited: tuple[Parameter, ...], own: tuple[Parameter, ...],
) -> tuple[Parameter, ...]:
    """
    Path-level parameters overlaid with an operation's own.

    A parameter is identified by name and location, and the operation wins.
    Inherited order is kept, so path parameters come before the operation's own.
    """
    merged: dict[tuple[str, ParameterLocation], Parameter] = {
        (parameter.name, parameter.location): parameter for parameter in inherited
    }
    for parameter in own:
        merged[(parameter.name, parameter.location)] = parameter
    return tuple(merged.values())


def read_response(
    code: str, raw: Any, operation: Mapping[str, Any], dialect,
    resolver: RefResolver, report: Reporter,
) -> Response | None:
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    return Response(
        status_code=code,
        description=read_str(raw, "description", report),
        headers=read_headers(raw, dialect, resolver, report),
        content=dialect.response_content(raw, operation, report),
        extensions=extensions_of(raw),
    )


def read_responses(
    raw: Any, operation: Mapping[str, Any], dialect,
    resolver: RefResolver, report: Reporter,
) -> tuple[Response, ...]:
    if raw is None:
        return ()
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return ()

    responses: list[Response] = []
    for code, value in raw.items():
        if str(code).startswith("x-"):
            continue
        at = report.at(code)
        response = read_response(
            str(code), resolver.resolve(value, at), operation, dialect, resolver, at,
        )
        if response is not None:
            responses.append(response)
    return tuple(responses)


def read_operation(
    path: str, method: HttpMethod, raw: Mapping[str, Any],
    inherited_parameters: tuple[Parameter, ...], dialect,
    resolver: RefResolver, report: Reporter,
) -> Operation:
    own = read_parameters(raw.get("parameters"), dialect, resolver, report.at("parameters"))
    return Operation(
        method=method,
        path=path,
        operation_id=read_str(raw, "operationId", report),
        summary=read_str(raw, "summary", report),
        description=read_str(raw, "description", report),
        tags=read_str_tuple(raw, "tags", report),
        deprecated=bool(read_bool(raw, "deprecated", report)),
        parameters=merge_parameters(inherited_parameters, own),
        request_body=dialect.request_body(raw, report),
        responses=read_responses(
            raw.get("responses"), raw, dialect, resolver, report.at("responses"),
        ),
        # Absent means "inherit the document's"; an empty list opts out.
        security=(
            read_requirements(raw["security"], report.at("security"))
            if "security" in raw else None
        ),
        servers=read_servers(raw.get("servers"), report.at("servers")),
        external_docs=read_external_docs(
            raw.get("externalDocs"), report.at("externalDocs"),
        ),
        extensions=extensions_of(raw),
    )


def read_path_item(
    path: str, raw: Any, dialect, resolver: RefResolver, report: Reporter,
) -> PathItem | None:
    raw = resolver.resolve(raw, report)
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None

    parameters = read_parameters(
        raw.get("parameters"), dialect, resolver, report.at("parameters"),
    )
    operations = tuple(
        read_operation(
            path, method, raw[method.value], parameters, dialect,
            resolver, report.at(method.value),
        )
        for method in HttpMethod
        if is_mapping(raw.get(method.value))
    )
    return PathItem(
        path=path,
        summary=read_str(raw, "summary", report),
        description=read_str(raw, "description", report),
        operations=operations,
        parameters=parameters,
        servers=read_servers(raw.get("servers"), report.at("servers")),
        extensions=extensions_of(raw),
    )


def read_paths(
    raw: Any, dialect, resolver: RefResolver, report: Reporter,
) -> tuple[PathItem, ...]:
    if raw is None:
        return ()
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return ()

    items: list[PathItem] = []
    for path, value in raw.items():
        if str(path).startswith("x-"):
            continue
        item = read_path_item(str(path), value, dialect, resolver, report.at(path))
        if item is not None:
            items.append(item)
    return tuple(items)
