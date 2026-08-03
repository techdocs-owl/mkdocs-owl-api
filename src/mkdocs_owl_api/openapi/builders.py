"""
OpenAPI-specific part builders.

`servers` here is a **list** of `{url, description, variables}`; the AsyncAPI
one is a dict keyed by server name. The two share nothing but the word.
"""

from __future__ import annotations

from typing import Any

from ..common.base import PartBuilder, RenderContext
from ..common.builders import SecurityBuilder
from ..common.primitives import (
    _anchor,
    _build_description_block,
    _demote_headings,
    _format_type,
    _heading,
    _html_table,
    _md_to_html,
    _pill,
    _ref_link,
)

HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options", "trace")

#: Tag used to group operations that declare none of their own.
DEFAULT_TAG = "Endpoints"


def _method_pill(method: str) -> str:
    return _pill(method.upper(), kind=f"http-{method}")


class ServersBuilder(PartBuilder):
    """The `## Servers` section. `servers` is a list, rendered as bullets."""

    def build(self) -> list[str]:
        servers = self.spec.get("servers")
        if not isinstance(servers, list) or not servers:
            return []

        bullets: list[str] = []
        for server in servers:
            if not isinstance(server, dict):
                continue
            url = server.get("url", "")
            desc = (server.get("description") or "").strip()
            bullets.append(f"- `{url}`" + (f" — {desc}" if desc else ""))

            variables = server.get("variables")
            if not isinstance(variables, dict) or not variables:
                continue
            for name, variable in variables.items():
                if not isinstance(variable, dict):
                    continue
                bits: list[str] = []
                if variable.get("default") is not None:
                    bits.append(f"default `{variable['default']}`")
                enum = variable.get("enum")
                if isinstance(enum, list) and enum:
                    bits.append("one of " + ", ".join(f"`{e}`" for e in enum))
                vdesc = (variable.get("description") or "").strip()
                if vdesc:
                    bits.append(vdesc)
                suffix = (" — " + "; ".join(bits)) if bits else ""
                bullets.append(f"    - `{{{name}}}`{suffix}")

        return ["## Servers", "\n".join(bullets)] if bullets else ["## Servers"]


class ParametersBuilder(PartBuilder):
    """
    An operation's parameters, as a Name/In/Type/Description table.

    Still its own traversal. Normalising the parameter list into an object
    schema so this can delegate to `SchemaTableBuilder` - and turning `In` into
    grouping rather than a column - is a behaviour change with its own commit.
    """

    HEADERS = ("Name", "In", "Type", "Description")

    def __init__(self, ctx: RenderContext, params: list[Any]):
        super().__init__(ctx)
        self._params = params

    def build(self) -> list[str]:
        rows: list[str] = []
        for param in self._params:
            if not isinstance(param, dict):
                continue
            schema = param.get("schema") or {}

            name_md = f"`{param.get('name', '')}`"
            pills: list[str] = []
            if param.get("required"):
                pills.append(_pill("required", kind="required"))
            if param.get("deprecated") or schema.get("deprecated"):
                pills.append(_pill("deprecated", kind="deprecated"))
            if pills:
                name_md += "<br>" + " ".join(pills)

            # The parameter-level description/example override the schema's.
            # Hoisting this merge from per-row to per-table is what lets
            # `SchemaTableBuilder` take over later.
            merged = dict(schema)
            pdesc = (param.get("description") or "").strip()
            if pdesc:
                merged["description"] = pdesc
            if param.get("example") is not None and "example" not in merged:
                merged["example"] = param["example"]

            desc_block = _build_description_block(merged)

            name_html = _md_to_html(name_md, inline=True)
            in_html = _md_to_html("`" + str(param.get("in", "")) + "`", inline=True)
            type_html = _md_to_html(_format_type(schema), inline=True)
            desc_html = _md_to_html(desc_block) if desc_block else "&mdash;"
            rows.append(
                f"<tr><td>{name_html}</td><td>{in_html}</td>"
                f"<td>{type_html}</td><td>{desc_html}</td></tr>"
            )

        return [_html_table(self.HEADERS, rows)] if rows else []


class RequestBuilder(PartBuilder):
    """
    An operation's request body.

    Emits the content type and the schema reference only - no property table.
    Wiring in `SchemaTableBuilder` here is a feature gain and gets its own
    commit.
    """

    def __init__(self, ctx: RenderContext, request_body: dict[str, Any]):
        super().__init__(ctx)
        self._request_body = request_body if isinstance(request_body, dict) else {}

    def build(self) -> list[str]:
        rb = self._request_body
        if not rb:
            return []

        blocks: list[str] = []
        desc = (rb.get("description") or "").strip()
        if desc:
            blocks.append(desc)

        for media_type, media_obj in (rb.get("content") or {}).items():
            blocks.append(f"*Content type:* {_pill(media_type, kind='contenttype')}")
            schema = (media_obj or {}).get("schema") or {}
            if "$ref" in schema:
                blocks.append(f"*Schema:* {_ref_link(schema['$ref'])}")
            elif schema.get("type"):
                blocks.append(f"*Schema:* {_format_type(schema)}")

        return blocks


class ResponsesBuilder(PartBuilder):
    """
    An operation's responses, as a Status/Description/Schema index.

    Not a property table - the rows are status codes, and no normalisation
    makes `200` a property name. Expanding each body through
    `SchemaTableBuilder` is a separate UX decision.
    """

    HEADERS = ("Status", "Description", "Schema")

    def __init__(self, ctx: RenderContext, responses: dict[str, Any]):
        super().__init__(ctx)
        self._responses = responses if isinstance(responses, dict) else {}

    def build(self) -> list[str]:
        if not self._responses:
            return []

        rows: list[str] = []
        for code, response in self._responses.items():
            if not isinstance(response, dict):
                continue

            desc = (response.get("description") or "").strip()
            desc_html = _md_to_html(desc, inline=True) if desc else "&mdash;"

            bits: list[tuple[str, str]] = []
            for media_type, media_obj in (response.get("content") or {}).items():
                schema = (media_obj or {}).get("schema") or {}
                if "$ref" in schema:
                    bits.append((media_type, _ref_link(schema["$ref"])))
                elif schema.get("type"):
                    bits.append((media_type, _format_type(schema)))
                else:
                    bits.append((media_type, "`object`"))

            if len(bits) == 1:
                schema_html = _md_to_html(bits[0][1], inline=True)
            elif bits:
                schema_html = _md_to_html(
                    "<br>".join(f"`{mt}`: {sch}" for mt, sch in bits), inline=True,
                )
            else:
                schema_html = "&mdash;"

            code_html = _md_to_html("`" + str(code) + "`", inline=True)
            rows.append(
                f"<tr><td>{code_html}</td><td>{desc_html}</td><td>{schema_html}</td></tr>"
            )

        return ["**Responses**", _html_table(self.HEADERS, rows)] if rows else []


class EndpointBuilder(PartBuilder):
    """One operation: heading, method pill, parameters, body, responses, security."""

    def __init__(
        self,
        ctx: RenderContext,
        *,
        path: str,
        method: str,
        operation: dict[str, Any],
        path_params: list[Any],
        tag_name: str,
    ):
        super().__init__(ctx)
        self._path = path
        self._method = method
        self._operation = operation
        self._path_params = path_params
        self._tag_name = tag_name

    def build(self) -> list[str]:
        op = self._operation
        summary = (op.get("summary") or "").strip()

        method_line = f"{_method_pill(self._method)} `{self._path}`"
        if op.get("deprecated"):
            method_line += " " + _pill("deprecated", kind="deprecated")

        blocks: list[str] = [
            _heading(
                3,
                summary or f"`{self._path}`",
                anchor=_anchor(
                    "endpoints", f"{self._tag_name}-{self._method}-{self._path}",
                ),
            ),
            method_line,
        ]

        desc = (op.get("description") or "").strip()
        if desc:
            blocks.append(_demote_headings(desc))

        params = list(self._path_params) + list(op.get("parameters") or [])
        if params:
            blocks.append("**Parameters**")
            blocks.extend(ParametersBuilder(self.ctx, params).build())

        request_body = op.get("requestBody") or {}
        if request_body:
            blocks.append("**Request body**")
            blocks.extend(RequestBuilder(self.ctx, request_body).build())

        blocks.extend(ResponsesBuilder(self.ctx, op.get("responses") or {}).build())

        security = op.get("security")
        if isinstance(security, list) and security:
            entries: list[str] = []
            for entry in security:
                entries.extend(SecurityBuilder(self.ctx, entry).build())
            if entries:
                blocks.append("**Security**")
                blocks.extend(entries)

        return blocks


class EndpointsBuilder(PartBuilder):
    """
    Every operation in `paths`, grouped under a `## tag` heading.

    An operation carrying several tags is rendered once per tag, which is what
    makes the anchor tag-scoped.
    """

    def build(self) -> list[str]:
        paths = self.spec.get("paths") or {}
        if not paths:
            return []

        tag_descriptions: dict[str, str] = {}
        for tag in self.spec.get("tags") or []:
            if isinstance(tag, dict) and tag.get("name"):
                tag_descriptions[tag["name"]] = (tag.get("description") or "").strip()

        grouped: dict[str, list[tuple[str, str, dict, list]]] = {}
        for path, path_obj in paths.items():
            if not isinstance(path_obj, dict):
                continue
            path_params = path_obj.get("parameters") or []
            for method in HTTP_METHODS:
                op = path_obj.get(method)
                if not isinstance(op, dict):
                    continue
                for tag in op.get("tags") or [DEFAULT_TAG]:
                    grouped.setdefault(tag, []).append((path, method, op, path_params))

        blocks: list[str] = []
        for tag_name, operations in grouped.items():
            blocks.append(_heading(2, tag_name, anchor=_anchor("tag", tag_name)))
            tag_desc = tag_descriptions.get(tag_name, "")
            if tag_desc:
                blocks.append(_demote_headings(tag_desc))
            for path, method, op, path_params in operations:
                blocks.extend(EndpointBuilder(
                    self.ctx,
                    path=path,
                    method=method,
                    operation=op,
                    path_params=path_params,
                    tag_name=tag_name,
                ).build())
        return blocks
