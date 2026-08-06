"""
The four places 2.0 and 3.x describe the same thing differently.

Everything else is shared traversal in `document.py`. A dialect is built once
per document and closes over the root, which is what keeps 2.0's inherited
`consumes`, `produces`, `schemes`, `host` and `basePath` out of every signature
downstream.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from ...common.parse_report import Reporter
from ...common.parse_util import (
    is_mapping,
    kind_of,
    read_bool,
    read_mapping,
    read_str,
    read_str_tuple,
)
from ...common.schema_model import UNSET, Schema
from ...common.schema_parser import read_schema
from ..model import (
    Components,
    MediaType,
    OpenApiDialect,
    RequestBody,
    Server,
)
from .document import (
    read_content,
    read_example,
    read_header,
    read_parameter,
    read_response,
    read_servers,
)
from .refs import RefResolver
from .security import read_v2_scheme, read_v3_scheme

#: Schema keywords a 2.0 parameter or header carries directly, rather than
#: under a `schema`. `collectionFormat` is missing on purpose: it describes
#: serialisation, not the value, and belongs on the parameter.
_V2_INLINE_SCHEMA_KEYS = frozenset({
    "default", "enum", "exclusiveMaximum", "exclusiveMinimum", "format",
    "items", "maxItems", "maxLength", "maximum", "minItems", "minLength",
    "minimum", "multipleOf", "pattern", "type", "uniqueItems", "x-nullable",
})

_DEFAULT_CONSUMES = "application/json"
_DEFAULT_PRODUCES = "application/json"
_DEFAULT_FORM_TYPE = "application/x-www-form-urlencoded"
_MULTIPART = "multipart/form-data"


class Dialect(Protocol):
    """What a version-specific reader must provide."""

    version: OpenApiDialect

    def servers(self, report: Reporter) -> tuple: ...
    def schema_of(self, raw: Mapping[str, Any], report: Reporter) -> Schema | None: ...
    def request_body(
        self, operation: Mapping[str, Any], report: Reporter,
    ) -> RequestBody | None: ...
    def response_content(
        self, response: Mapping[str, Any], operation: Mapping[str, Any],
        report: Reporter,
    ) -> dict[str, MediaType]: ...
    def components(self, report: Reporter) -> Components: ...


class OpenApi3Dialect:
    """OpenAPI 3.0 and 3.1, which differ only inside a schema - and so not here."""

    def __init__(self, root: Mapping[str, Any], resolver: RefResolver,
                 version: OpenApiDialect):
        self._root = root
        self._resolver = resolver
        self.version = version

    def servers(self, report: Reporter) -> tuple:
        return read_servers(self._root.get("servers"), report.at("servers"))

    def schema_of(self, raw: Mapping[str, Any], report: Reporter) -> Schema | None:
        if "schema" not in raw:
            return None
        return read_schema(raw["schema"], report.at("schema"))

    def request_body(
        self, operation: Mapping[str, Any], report: Reporter,
    ) -> RequestBody | None:
        if "requestBody" not in operation:
            return None
        at = report.at("requestBody")
        raw = self._resolver.resolve(operation["requestBody"], at)
        if not is_mapping(raw):
            at.warn(f"expected an object, found {kind_of(raw)}")
            return None
        return RequestBody(
            description=read_str(raw, "description", at),
            required=bool(read_bool(raw, "required", at)),
            content=read_content(raw, self, self._resolver, at),
        )

    def response_content(
        self, response: Mapping[str, Any], operation: Mapping[str, Any],
        report: Reporter,
    ) -> dict[str, MediaType]:
        return read_content(response, self, self._resolver, report)

    def components(self, report: Reporter) -> Components:
        raw = read_mapping(self._root, "components", report) or {}
        at = report.at("components")
        resolver = self._resolver

        def each(key: str, reader):
            node = read_mapping(raw, key, at) or {}
            built = {}
            for name, value in node.items():
                item = reader(str(name), value, at.at(key, name))
                if item is not None:
                    built[str(name)] = item
            return built

        return Components(
            schemas=each("schemas", lambda n, v, w: read_schema(v, w)),
            responses=each("responses", lambda n, v, w: read_response(
                "", resolver.resolve(v, w), {}, self, resolver, w)),
            parameters=each("parameters", lambda n, v, w: read_parameter(
                resolver.resolve(v, w), self, resolver, w)),
            examples=each("examples", lambda n, v, w: read_example(
                resolver.resolve(v, w), w)),
            request_bodies=each("requestBodies", lambda n, v, w: self._component_body(v, w)),
            headers=each("headers", lambda n, v, w: read_header(
                resolver.resolve(v, w), self, resolver, w)),
            security_schemes=each("securitySchemes", lambda n, v, w: (
                read_v3_scheme(n, v, w) if is_mapping(v) else None)),
        )

    def _component_body(self, raw: Any, report: Reporter) -> RequestBody | None:
        raw = self._resolver.resolve(raw, report)
        if not is_mapping(raw):
            report.warn(f"expected an object, found {kind_of(raw)}")
            return None
        return RequestBody(
            description=read_str(raw, "description", report),
            required=bool(read_bool(raw, "required", report)),
            content=read_content(raw, self, self._resolver, report),
        )


class Swagger2Dialect:
    """
    OpenAPI 2.0.

    The restructurings live here: a server assembled from three root keys, a
    request body lifted out of the parameter list, response bodies crossed with
    `produces`, and schema keywords that sit directly on a parameter.
    """

    version = OpenApiDialect.V2_0

    def __init__(self, root: Mapping[str, Any], resolver: RefResolver):
        self._root = root
        self._resolver = resolver

    def servers(self, report: Reporter) -> tuple:
        host = read_str(self._root, "host", report) or ""
        base_path = read_str(self._root, "basePath", report) or ""
        schemes = read_str_tuple(self._root, "schemes", report)

        if not host and not base_path:
            return ()
        if not schemes:
            # No scheme is stated and the document's own URL is not knowable
            # here, so the reference stays protocol-relative.
            url = f"//{host}{base_path}" if host else base_path
            return (Server(url=url),)
        return tuple(
            Server(url=f"{scheme}://{host}{base_path}") for scheme in schemes
        )

    def schema_of(self, raw: Mapping[str, Any], report: Reporter) -> Schema | None:
        """
        A body parameter nests its schema; everything else spells it inline.
        """
        if "schema" in raw:
            return read_schema(raw["schema"], report.at("schema"))
        inline = {key: raw[key] for key in raw if key in _V2_INLINE_SCHEMA_KEYS}
        return read_schema(inline, report) if inline else None

    def _media_types(
        self, operation: Mapping[str, Any], key: str, report: Reporter,
    ) -> tuple[str, ...]:
        """`consumes`/`produces`, with the operation overriding the document."""
        if key in operation:
            return read_str_tuple(operation, key, report)
        if key in self._root:
            return read_str_tuple(self._root, key, report)
        return ()

    def request_body(
        self, operation: Mapping[str, Any], report: Reporter,
    ) -> RequestBody | None:
        raw_parameters = operation.get("parameters")
        if not isinstance(raw_parameters, list):
            return None

        body: Mapping[str, Any] | None = None
        form: list[tuple[int, Mapping[str, Any]]] = []
        for index, entry in enumerate(raw_parameters):
            at = report.at("parameters", index)
            resolved = self._resolver.resolve(entry, at)
            if not is_mapping(resolved):
                continue
            if resolved.get("in") == "body":
                body = resolved
            elif resolved.get("in") == "formData":
                form.append((index, resolved))

        if body is not None:
            return self._body_from_parameter(body, operation, report)
        if form:
            return self._body_from_form(form, operation, report)
        return None

    def _body_from_parameter(
        self, raw: Mapping[str, Any], operation: Mapping[str, Any], report: Reporter,
    ) -> RequestBody:
        at = report.at("parameters", "body")
        schema = self.schema_of(raw, at)
        media_types = self._media_types(operation, "consumes", report) or (_DEFAULT_CONSUMES,)
        return RequestBody(
            description=read_str(raw, "description", at),
            required=bool(read_bool(raw, "required", at)),
            content={name: MediaType(schema=schema) for name in media_types},
        )

    def _body_from_form(
        self, form: list[tuple[int, Mapping[str, Any]]],
        operation: Mapping[str, Any], report: Reporter,
    ) -> RequestBody:
        """
        Form fields, gathered into the object schema 3.x would have written.
        """
        properties: dict[str, Schema] = {}
        required: list[str] = []
        has_file = False

        for index, raw in form:
            at = report.at("parameters", index)
            name = read_str(raw, "name", at)
            if not name:
                at.warn("no `name`")
                continue
            schema = self.schema_of(raw, at)
            if schema is not None:
                properties[name] = schema
            if read_bool(raw, "required", at):
                required.append(name)
            if raw.get("type") == "file":
                has_file = True

        default_type = _MULTIPART if has_file else _DEFAULT_FORM_TYPE
        media_types = self._media_types(operation, "consumes", report) or (default_type,)
        schema = Schema(
            types=("object",), properties=properties, required=tuple(required),
        )
        return RequestBody(
            required=bool(required),
            content={name: MediaType(schema=schema) for name in media_types},
        )

    def response_content(
        self, response: Mapping[str, Any], operation: Mapping[str, Any],
        report: Reporter,
    ) -> dict[str, MediaType]:
        schema = (
            read_schema(response["schema"], report.at("schema"))
            if "schema" in response else None
        )
        examples = read_mapping(response, "examples", report) or {}
        if schema is None and not examples:
            return {}

        media_types = self._media_types(operation, "produces", report)
        names = list(media_types) or [_DEFAULT_PRODUCES]
        for name in examples:
            if str(name) not in names:
                names.append(str(name))

        return {
            name: MediaType(
                schema=schema,
                example=examples[name] if name in examples else UNSET,
            )
            for name in names
        }

    def components(self, report: Reporter) -> Components:
        root = self._root
        resolver = self._resolver

        def each(key: str, reader):
            node = read_mapping(root, key, report) or {}
            built = {}
            for name, value in node.items():
                item = reader(str(name), value, report.at(key, name))
                if item is not None:
                    built[str(name)] = item
            return built

        return Components(
            schemas=each("definitions", lambda n, v, w: read_schema(v, w)),
            responses=each("responses", lambda n, v, w: read_response(
                "", resolver.resolve(v, w), {}, self, resolver, w)),
            parameters=each("parameters", lambda n, v, w: read_parameter(
                resolver.resolve(v, w), self, resolver, w)),
            security_schemes=each("securityDefinitions", lambda n, v, w: (
                read_v2_scheme(n, v, w) if is_mapping(v) else None)),
        )
