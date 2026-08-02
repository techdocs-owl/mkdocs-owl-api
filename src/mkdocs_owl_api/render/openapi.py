"""
OpenAPI 3.x page renderer.
"""

from __future__ import annotations

from typing import Any

from ..options import PageOptions
from .common import (
    _anchor,
    _build_description_block,
    _demote_headings,
    _format_type,
    _heading,
    _md_to_html,
    _pill,
    _ref_link,
    _render_downloads_table,
    _render_schema,
    _render_security_inline,
)

_HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options", "trace")


def _openapi_method_pill(method: str) -> str:
    return _pill(method.upper(), kind=f"http-{method}")


def _openapi_render_parameters(params: list[dict[str, Any]]) -> str:
    if not params:
        return ""
    parts: list[str] = [
        '<table>',
        '<thead>',
        '<tr><th>Name</th><th>In</th><th>Type</th><th>Description</th></tr>',
        '</thead>',
        '<tbody>',
    ]
    for p in params:
        if not isinstance(p, dict):
            continue
        name = p.get("name", "")
        in_ = p.get("in", "")
        schema = p.get("schema") or {}
        type_str = _format_type(schema)

        name_md = f"`{name}`"
        pills: list[str] = []
        if p.get("required"):
            pills.append(_pill("required", kind="required"))
        if p.get("deprecated") or schema.get("deprecated"):
            pills.append(_pill("deprecated", kind="deprecated"))
        if pills:
            name_md += "<br>" + " ".join(pills)
        name_html = _md_to_html(name_md, inline=True)

        type_html = _md_to_html(type_str, inline=True)

        merged = dict(schema)
        pdesc = (p.get("description") or "").strip()
        if pdesc:
            merged["description"] = pdesc
        if p.get("example") is not None and "example" not in merged:
            merged["example"] = p["example"]
        desc_block = _build_description_block(merged)
        desc_html = _md_to_html(desc_block) if desc_block else "&mdash;"

        in_html = _md_to_html(f"`{in_}`", inline=True)
        parts.append(f"<tr><td>{name_html}</td><td>{in_html}</td><td>{type_html}</td><td>{desc_html}</td></tr>")
    parts.append('</tbody>')
    parts.append('</table>')
    parts.append("")
    return "\n".join(parts)


def _openapi_render_request_body(rb: dict[str, Any], spec: dict[str, Any], *, hide_internal: bool) -> str:
    if not rb:
        return ""
    parts: list[str] = []
    desc = (rb.get("description") or "").strip()
    if desc:
        parts.append(desc)
        parts.append("")
    content = rb.get("content") or {}
    for media_type, media_obj in content.items():
        parts.append(f"*Content type:* {_pill(media_type, kind='contenttype')}")
        parts.append("")
        schema = (media_obj or {}).get("schema") or {}
        if "$ref" in schema:
            parts.append(f"*Schema:* {_ref_link(schema['$ref'])}")
            parts.append("")
        elif schema.get("type"):
            parts.append(f"*Schema:* {_format_type(schema)}")
            parts.append("")
    return "\n".join(parts)


def _openapi_render_responses(responses: dict[str, Any], spec: dict[str, Any]) -> str:
    if not responses:
        return ""
    parts: list[str] = [
        "**Responses**",
        "",
        '<table>',
        '<thead>',
        '<tr><th>Status</th><th>Description</th><th>Schema</th></tr>',
        '</thead>',
        '<tbody>',
    ]
    for code, resp in responses.items():
        if not isinstance(resp, dict):
            continue
        desc = (resp.get("description") or "").strip()
        desc_html = _md_to_html(desc, inline=True) if desc else "&mdash;"
        schema_html = "&mdash;"
        content = resp.get("content") or {}
        bits: list[tuple[str, str]] = []
        for mt, media_obj in content.items():
            schema = (media_obj or {}).get("schema") or {}
            if "$ref" in schema:
                bits.append((mt, _ref_link(schema["$ref"])))
            elif schema.get("type"):
                bits.append((mt, _format_type(schema)))
            else:
                bits.append((mt, "`object`"))
        if len(bits) == 1:
            schema_html = _md_to_html(bits[0][1], inline=True)
        elif bits:
            schema_html = _md_to_html(
                "<br>".join(f"`{mt}`: {sch}" for mt, sch in bits), inline=True,
            )
        code_html = _md_to_html(f"`{code}`", inline=True)
        parts.append(f"<tr><td>{code_html}</td><td>{desc_html}</td><td>{schema_html}</td></tr>")
    parts.append('</tbody>')
    parts.append('</table>')
    parts.append("")
    return "\n".join(parts)


def _render_openapi_page(
    spec: dict[str, Any],
    opts: PageOptions,
    *,
    spec_url: str = "",
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    info = spec.get("info") or {}
    title = (opts.title or info.get("title") or "API Reference").strip()
    intro = opts.intro
    parts: list[str] = [f"# {title}", ""]

    if intro:
        parts.append(intro)
        parts.append("")

    version = (info.get("version") or "").strip()
    if version and not opts.hide_version:
        parts.append(f"**Version:** `{version}`")
        parts.append("")

    downloads = _render_downloads_table(
        spec_url, attachments or [], hide_download=(opts.hide_download_link), spec_type="OpenAPI")
    if downloads:
        parts.append(downloads)

    description = (info.get("description") or "").strip()
    if description:
        parts.append(_demote_headings(description))
        parts.append("")

    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        parts.append("## Servers")
        parts.append("")
        for srv in servers:
            if not isinstance(srv, dict):
                continue
            url = srv.get("url", "")
            desc = (srv.get("description") or "").strip()
            parts.append(f"- `{url}`" + (f" — {desc}" if desc else ""))
            variables = srv.get("variables")
            if isinstance(variables, dict) and variables:
                for vname, v in variables.items():
                    if not isinstance(v, dict):
                        continue
                    bits: list[str] = []
                    if v.get("default") is not None:
                        bits.append(f"default `{v['default']}`")
                    enum = v.get("enum")
                    if isinstance(enum, list) and enum:
                        bits.append("one of " + ", ".join(f"`{e}`" for e in enum))
                    vdesc = (v.get("description") or "").strip()
                    if vdesc:
                        bits.append(vdesc)
                    suffix = (" — " + "; ".join(bits)) if bits else ""
                    parts.append(f"    - `{{{vname}}}`{suffix}")
        parts.append("")

    paths = spec.get("paths") or {}
    if paths:
        tag_descriptions: dict[str, str] = {}
        for t in (spec.get("tags") or []):
            if isinstance(t, dict) and t.get("name"):
                tag_descriptions[t["name"]] = (t.get("description") or "").strip()

        _DEFAULT_TAG = "Endpoints"
        grouped: dict[str, list[tuple[str, str, dict, list]]] = {}
        for path, path_obj in paths.items():
            if not isinstance(path_obj, dict):
                continue
            path_params = path_obj.get("parameters") or []
            for method in _HTTP_METHODS:
                op = path_obj.get(method)
                if not isinstance(op, dict):
                    continue
                tags = op.get("tags") or [_DEFAULT_TAG]
                for tag in tags:
                    grouped.setdefault(tag, []).append((path, method, op, path_params))

        for tag_name, ops in grouped.items():
            parts.append(_heading(2, tag_name, anchor=_anchor("tag", tag_name)))
            parts.append("")
            tag_desc = tag_descriptions.get(tag_name, "")
            if tag_desc:
                parts.append(_demote_headings(tag_desc))
                parts.append("")

            for path, method, op, path_params in ops:
                summary = (op.get("summary") or "").strip()
                heading_text = summary or f"`{path}`"
                anchor = _anchor("endpoints", f"{tag_name}-{method}-{path}")
                parts.append(_heading(3, heading_text, anchor=anchor))
                parts.append("")
                method_line = f"{_openapi_method_pill(method)} `{path}`"
                if op.get("deprecated"):
                    method_line += " " + _pill("deprecated", kind="deprecated")
                parts.append(method_line)
                parts.append("")

                desc = (op.get("description") or "").strip()
                if desc:
                    parts.append(_demote_headings(desc))
                    parts.append("")

                op_params = op.get("parameters") or []
                all_params = path_params + op_params
                if all_params:
                    parts.append("**Parameters**")
                    parts.append("")
                    parts.append(_openapi_render_parameters(all_params))

                rb = op.get("requestBody") or {}
                if rb:
                    parts.append("**Request body**")
                    parts.append("")
                    parts.append(_openapi_render_request_body(rb, spec, hide_internal=(opts.hide_internal)))

                responses = op.get("responses") or {}
                if responses:
                    parts.append(_openapi_render_responses(responses, spec))

                security = op.get("security")
                if isinstance(security, list) and security:
                    blocks = [b for b in (_render_security_inline(spec, e) for e in security) if b]
                    if blocks:
                        parts.append("**Security**")
                        parts.append("")
                        for b in blocks:
                            parts.append(b)
                            parts.append("")

    schemas = (spec.get("components") or {}).get("schemas") or {}
    if schemas:
        max_depth = opts.schema_depth
        parts.append("## Schemas")
        parts.append("")
        for sname, sch in schemas.items():
            if not isinstance(sch, dict):
                continue
            parts.append(_heading(3, sname, anchor=_anchor("schemas", sname)))
            parts.append("")
            parts.append(_render_schema(sch, hide_internal=(opts.hide_internal), max_depth=max_depth))
            parts.append("")

    while parts and parts[-1] in ("", "---"):
        parts.pop()

    return "\n".join(parts)
