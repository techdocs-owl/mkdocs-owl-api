"""
OpenAPI page renderer, driven by the model.

`MarkdownRenderer` holds what is constant for a page - the options, and the set
of schema names that can be linked to - and each section is a method returning
blocks. Anything needing no page state is a function in `jsonschema.schema_render`.

The renderer never learns which dialect the description came from: a 2.0 file
and a 3.1 file that describe the same API produce the same page.
"""

from __future__ import annotations

from dataclasses import replace

from ..common.render import MarkdownRenderer
from ..common.primitives.markup import (
    _anchor,
    _demote_headings,
    _heading,
    _html_table,
    _md_to_html,
)
from ..common.primitives.pills import (
    content_type_pill,
    deprecated_pill,
    pill_blue,
    pill_green,
    pill_grey,
    pill_orange,
    pill_purple,
    pill_red,
    required_pill,
    scheme_pill,
)
from ..model.jsonschema.schema_types import UNSET, Schema
from ..jsonschema.schema_render import (
    describe,
    format_type,
    property_rows,
    property_table,
    render_schema,
)
from ..model.openapi.types import (
    HttpMethod, OpenApiDoc, MediaType, Operation, Parameter, Response, Server,
)

#: Section for operations that declare no tag of their own.
DEFAULT_TAG = "Endpoints"

PARAMETER_HEADERS = ("Name", "In", "Type", "Description")
RESPONSE_HEADERS = ("Status", "Description", "Schema")
HEADER_HEADERS = ("Header", "Type", "Description")

_METHOD_PILLS = {
    HttpMethod.GET: pill_green,
    HttpMethod.POST: pill_blue,
    HttpMethod.PUT: pill_orange,
    HttpMethod.DELETE: pill_red,
    HttpMethod.PATCH: pill_purple,
}


def method_pill(method: HttpMethod) -> str:
    return _METHOD_PILLS.get(method, pill_grey)(method.value.upper())


class OpenApiRenderer(MarkdownRenderer):
    """Servers, endpoints grouped by tag, then the named schemas."""

    doc: OpenApiDoc

    def sections(self) -> list[str]:
        return self.servers() + self.endpoints() + self.schemas()

    # -- servers ------------------------------------------------------------

    def servers(self) -> list[str]:
        if not self.doc.servers:
            return []
        bullets: list[str] = []
        for server in self.doc.servers:
            bullets.extend(self._server_bullets(server))
        return ["## Servers", "\n".join(bullets)]

    @staticmethod
    def _server_bullets(server: Server) -> list[str]:
        description = (server.description or "").strip()
        bullets = [f"- `{server.url}`" + (f" — {description}" if description else "")]
        for name, variable in server.variables.items():
            bits: list[str] = []
            if variable.default:
                bits.append(f"default `{variable.default}`")
            if variable.enum:
                bits.append("one of " + ", ".join(f"`{v}`" for v in variable.enum))
            if variable.description:
                bits.append(variable.description.strip())
            suffix = (" — " + "; ".join(bits)) if bits else ""
            bullets.append(f"    - `{{{name}}}`{suffix}")
        return bullets

    # -- endpoints ----------------------------------------------------------

    def endpoints(self) -> list[str]:
        grouped: dict[str, list[Operation]] = {}
        for path_item in self.doc.paths:
            for operation in path_item.operations:
                for tag in operation.tags or (DEFAULT_TAG,):
                    grouped.setdefault(tag, []).append(operation)
        if not grouped:
            return []

        described = {tag.name: (tag.description or "").strip()
                     for tag in self.doc.tags}

        blocks: list[str] = []
        for tag, operations in grouped.items():
            blocks.append(_heading(2, tag, anchor=_anchor("tag", tag)))
            if described.get(tag):
                blocks.append(_demote_headings(described[tag]))
            for operation in operations:
                blocks.extend(self.operation(operation, tag))
        return blocks

    def operation(self, operation: Operation, tag: str) -> list[str]:
        summary = (operation.summary or "").strip()
        method_line = f"{method_pill(operation.method)} `{operation.path}`"
        if operation.deprecated:
            method_line += " " + deprecated_pill()

        blocks = [
            _heading(3, summary or f"`{operation.path}`", anchor=_anchor(
                "endpoints", f"{tag}-{operation.method.value}-{operation.path}",
            )),
            method_line,
        ]

        description = (operation.description or "").strip()
        if description:
            blocks.append(_demote_headings(description))

        if operation.parameters:
            blocks.append("**Parameters**")
            blocks.extend(self.parameters(operation.parameters))

        if operation.request_body is not None:
            blocks.extend(self.request_body(operation.request_body))

        blocks.extend(self.responses(operation.responses))
        blocks.extend(self.security(operation))
        return blocks

    def parameters(self, parameters: tuple[Parameter, ...]) -> list[str]:
        rows: list[str] = []
        for parameter in parameters:
            pills: list[str] = []
            if parameter.required:
                pills.append(required_pill())
            if parameter.deprecated:
                pills.append(deprecated_pill())

            name_md = f"`{parameter.name}`"
            if pills:
                name_md += "<br>" + " ".join(pills)

            schema = parameter.schema or Schema()
            # A parameter's own description and example describe the parameter,
            # so they take precedence over the schema's.
            described = self._describe_with_overrides(
                schema, parameter.description, parameter.example,
            )

            rows.append(
                f"<tr><td>{_md_to_html(name_md, inline=True)}</td>"
                f"<td>{_md_to_html('`' + parameter.location.value + '`', inline=True)}</td>"
                f"<td>{_md_to_html(format_type(schema), inline=True)}</td>"
                f"<td>{_md_to_html(described) if described else '&mdash;'}</td></tr>"
            )
        return [_html_table(rows, headers=PARAMETER_HEADERS)] if rows else []

    @staticmethod
    def _describe_with_overrides(schema: Schema, description, example) -> str:
        merged = schema
        if description:
            merged = replace(merged, description=description)
        if example is not UNSET and not schema.examples:
            merged = replace(merged, examples=(example,))
        return describe(merged)

    def request_body(self, body) -> list[str]:
        blocks: list[str] = ["**Request body**"]
        description = (body.description or "").strip()
        if description:
            blocks.append(description)
        if body.required:
            blocks.append(required_pill())
        blocks.extend(self.content(body.content))
        return blocks

    def content(self, content: dict[str, MediaType]) -> list[str]:
        """
        One media type's schema. Named schemas are linked rather than expanded;
        an inline one gets its property table here, where it is the only place
        it appears.
        """
        blocks: list[str] = []
        for media_type, media in content.items():
            blocks.append(f"*Content type:* {content_type_pill(media_type)}")
            schema = media.schema
            if schema is None:
                continue
            blocks.append(f"*Schema:* {format_type(schema)}")
            if not schema.is_ref() and schema.properties:
                blocks.extend(property_table(property_rows(
                    schema, hide_internal=self.options.hide_internal,
                    max_depth=self.options.schema_depth,
                )))
        return blocks

    def responses(self, responses: tuple[Response, ...]) -> list[str]:
        if not responses:
            return []
        rows: list[str] = []
        for response in responses:
            description = (response.description or "").strip()
            bits = [(media_type, format_type(media.schema))
                    for media_type, media in response.content.items()
                    if media.schema is not None]
            if len(bits) == 1:
                schema_md = bits[0][1]
            elif bits:
                schema_md = "<br>".join(f"`{mt}`: {s}" for mt, s in bits)
            else:
                schema_md = ""

            rows.append(
                f"<tr><td>{_md_to_html('`' + response.status_code + '`', inline=True)}</td>"
                f"<td>{_md_to_html(description, inline=True) if description else '&mdash;'}</td>"
                f"<td>{_md_to_html(schema_md, inline=True) if schema_md else '&mdash;'}</td></tr>"
            )

        blocks = ["**Responses**", _html_table(rows, headers=RESPONSE_HEADERS)]
        for response in responses:
            blocks.extend(self.response_headers(response))
        return blocks

    def response_headers(self, response: Response) -> list[str]:
        """Response headers, which the model carries and a reader wants."""
        if not response.headers:
            return []
        rows = [
            f"<tr><td>{_md_to_html('`' + name + '`', inline=True)}</td>"
            f"<td>{_md_to_html(format_type(header.schema), inline=True)}</td>"
            f"<td>{_md_to_html(describe(replace(header.schema or Schema(), description=header.description))) or '&mdash;'}</td></tr>"
            for name, header in response.headers.items()
        ]
        return [f"*Headers for* `{response.status_code}`:",
                _html_table(rows, headers=HEADER_HEADERS)]

    def security(self, operation: Operation) -> list[str]:
        if self.options.hide_security:
            return []
        alternatives = (operation.security if operation.security is not None
                        else self.doc.security)
        if not alternatives:
            return []

        blocks: list[str] = ["**Security**"]
        for alternative in alternatives:
            for requirement in alternative:
                blocks.extend(self.security_scheme(requirement))
        return blocks

    def security_scheme(self, requirement) -> list[str]:
        scheme = self.doc.components.security_schemes.get(requirement.scheme_name)
        if scheme is None:
            return [f"- **Security:** `{requirement.scheme_name}`"]

        body: list[str] = [f"**Type:** {scheme_pill(scheme.type.value)}", ""]
        for label, value in (
            ("Name", scheme.parameter_name),
            ("In", scheme.location.value if scheme.location else None),
            ("Scheme", scheme.scheme),
            ("Bearer format", scheme.bearer_format),
            ("OpenID Connect URL", scheme.open_id_connect_url),
        ):
            if value:
                body.append(f"**{label}:** `{value}`")

        description = (scheme.description or "").strip()
        if description:
            if body[-1] != "":
                body.append("")
            body.append(_demote_headings(description, levels=2))

        if requirement.scopes:
            if body[-1] != "":
                body.append("")
            body.append("**Scopes:** " + ", ".join(f"`{s}`" for s in requirement.scopes))

        indented = "\n".join(("    " + line) if line else "" for line in body)
        return [f'!!! note ":material-security: Security: {requirement.scheme_name}"\n{indented}']

    # -- schemas ------------------------------------------------------------

    def schemas(self) -> list[str]:
        schemas = self.doc.components.schemas
        if not schemas:
            return []
        blocks: list[str] = ["## Schemas"]
        for name, schema in schemas.items():
            blocks.append(_heading(3, name, anchor=_anchor("schemas", name)))
            blocks.extend(render_schema(
                schema,
                hide_internal=self.options.hide_internal,
                max_depth=self.options.schema_depth,
            ))
        return blocks



