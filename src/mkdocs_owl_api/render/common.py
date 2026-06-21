"""
Shared rendering building blocks used by both the AsyncAPI and OpenAPI page renderers.
"""

from __future__ import annotations

import html as _html
import re
from typing import Any

import markdown as _md
import yaml

_CELL_MD = _md.Markdown(
    extensions=["fenced_code", "tables", "admonition", "attr_list"],
    output_format="html",
)


def _md_to_html(text: str, *, inline: bool = False) -> str:
    """
    Convert a Markdown fragment to HTML for direct embedding.

    Pass `inline=True` to strip a single wrapping `<p>...</p>` so the
    result sits cleanly in a single-line cell (used for name/type columns).
    Block content (descriptions with paragraphs, lists, code) keeps its
    natural HTML structure.
    """
    if not text or not text.strip():
        return ""
    _CELL_MD.reset()
    html = _CELL_MD.convert(_normalize_lists(text)).strip()
    if inline and html.startswith("<p>") and html.endswith("</p>"):
        html = html[3:-4]
    return html


def _pill(label: str, *, kind: str, title: str | None = None) -> str:
    """
    Render a short categorical badge as a `<span class="techdocs-owl-api-pill ...">`.
    """
    classes = f"techdocs-owl-api-pill techdocs-owl-api-pill--{kind}"
    title_attr = f' title="{_html.escape(title)}"' if title else ""
    return (
        f'<span class="{classes}"{title_attr}>'
        f'{_html.escape(label)}'
        f'</span>'
    )


def _unescape_pointer(token: str) -> str:
    """
    Decode a JSON Pointer reference token (RFC 6901): `~1` -> `/`, `~0` -> `~`.
    """
    return token.replace("~1", "/").replace("~0", "~")


def _resolve_ref(spec: dict[str, Any], ref: str) -> Any:
    """
    Walk a JSON-Pointer-style `$ref` against the loaded spec.

    Used for inlining referenced objects (e.g. embedding a security scheme body where it is referenced).
    """
    if not ref.startswith("#/"):
        return None
    node: Any = spec
    for part in ref[2:].split("/"):
        part = _unescape_pointer(part)
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


_LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])\s+")


def _normalize_lists(md: str) -> str:
    """
    Insert a blank line before a bullet/numbered list that directly follows a non-blank line.

    p.s. Python-Markdown is strict about list recognition: a `- item`.
    """
    if not md:
        return md
    out: list[str] = []
    in_fence = False
    prev_blank = True
    for line in md.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            prev_blank = False
            continue
        if not in_fence and _LIST_ITEM_RE.match(line) and not prev_blank:
            if not (out and _LIST_ITEM_RE.match(out[-1])):
                out.append("")
        out.append(line)
        prev_blank = (line.strip() == "")
    return "\n".join(out)


_FENCE_RE = re.compile(r"^[ \t]*(```+|~~~+)")
_HEADING_RE = re.compile(r"^#+\s+")


def _slug(name: str) -> str:
    """
    Match python-markdown's default toc slugifier closely enough for in-page anchor links to resolve.
    """
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _anchor(section: str, name: str) -> str:
    """
    Stable anchor id for an item rendered under a section heading.
    """
    return f"{_slug(section)}-{_slug(name)}"


def _heading(level: int, name: str, *, anchor: str | None = None) -> str:
    """
    Emit an ATX heading, optionally with an explicit attr_list id.

    Explicit ids decouple anchors from python-markdown's auto-slug rules,
    which is important here because two sections may legitimately share an
    item name (e.g. a schema and a message both called `User`).
    """
    line = f"{'#' * level} {name}"
    if anchor:
        line += f" {{#{anchor}}}"
    return line


def _ref_link(ref: str) -> str:
    """
    Resolve a JSON Pointer-style `$ref` to a Markdown link.

    The convention is that `parts[-2]` of the ref path is the section name
    and `parts[-1]` is the item name. Examples:

      '#/components/schemas/Foo'             -> [Foo](#schemas-foo)
      '#/components/messages/Light'          -> [Light](#messages-light)
      '#/channels/lightingMeasured'          -> [lightingMeasured](#channels-lightingmeasured)
      '#/channels/X/messages/Y'              -> [Y](#messages-y)
    """
    parts = [_unescape_pointer(p) for p in ref.lstrip("#/").split("/")]
    if not parts:
        return "`<broken-ref>`"
    if len(parts) < 2:
        return f"`{parts[-1]}`"
    name = parts[-1]
    section = parts[-2]
    return f"[`{name}`](#{_anchor(section, name)})"


def _demote_headings(md: str, levels: int = 2) -> str:
    """
    Add `levels` `#`s to ATX heading lines outside fenced code blocks.

    Spec descriptions are free-form Markdown and sometimes contain `##` headings that would collide with section headings.
    Shifting them down keeps the heading hierarchy clean.
    """
    if not md:
        return md
    prefix = "#" * levels
    out: list[str] = []
    in_fence = False
    for line in md.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and _HEADING_RE.match(line):
            line = prefix + line
        out.append(line)
    return "\n".join(out)


def _format_type(prop: dict[str, Any]) -> str:
    """
    Render a property's type as a short, readable expression.
    """
    if "$ref" in prop:
        return _ref_link(prop["$ref"])

    all_of = prop.get("allOf")
    if isinstance(all_of, list) and len(all_of) == 1:
        return f"array of {_format_type(all_of[0])}"

    t = prop.get("type")
    if isinstance(t, list):
        t = " | ".join(str(x) for x in t)
    fmt = prop.get("format")

    if t == "object" and "additionalProperties" in prop:
        return f"map of string → {_format_type(prop['additionalProperties'])}"
    if t == "array":
        return f"array of {_format_type(prop.get('items') or {})}"
    if t and fmt:
        return f"{t} ({fmt})"
    if t:
        return t
    return "object"


def _flags(prop: dict[str, Any]) -> list[str]:
    """
    Visible callouts for property-level annotations, rendered as pills.
    """
    flags: list[str] = []
    if prop.get("x-internal-only") is True:
        flags.append(_pill("internal", kind="internal"))
    if prop.get("deprecated") is True:
        flags.append(_pill("deprecated", kind="deprecated"))
    return flags


def _schema_depth(opts: dict[str, Any]) -> int:
    """
    How many levels deep inline object properties are flattened into the dot-path properties table.
    Configurable via the `schema_depth` frontmatter key.
    """
    raw = opts.get("schema_depth", 3)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 3


def _render_tags(tags: Any) -> str:
    if not isinstance(tags, list) or not tags:
        return ""
    pills: list[str] = []
    for tag in tags:
        if isinstance(tag, dict):
            nm = str(tag.get("name") or "tag")
            td = (tag.get("description") or "").strip() or None
            pills.append(_pill(nm, kind="tag", title=td))
        else:
            pills.append(_pill(str(tag), kind="tag"))
    return "**Tags:** " + " ".join(pills)


def _render_bindings(bindings: Any, *, hide_bindings: bool) -> str:
    if hide_bindings or not isinstance(bindings, dict) or not bindings:
        return ""
    parts: list[str] = []
    for protocol, body in bindings.items():
        parts.append(f'!!! note "{protocol} bindings"')
        rendered = yaml.safe_dump(
            body, sort_keys=False, default_flow_style=False
        ).rstrip()
        parts.append("    ```yaml")
        for line in rendered.split("\n"):
            parts.append("    " + line)
        parts.append("    ```")
        parts.append("")
    return "\n".join(parts)


def _render_examples(examples: Any) -> str:
    """
    Render `examples` as fenced code blocks.
    """
    if not examples:
        return ""
    if not isinstance(examples, list):
        examples = [examples]
    parts: list[str] = ["**Examples**", ""]
    for ex in examples:
        if isinstance(ex, dict) and "payload" in ex:
            label = ex.get("name") or ex.get("summary")
            payload = ex.get("payload")
        else:
            label = None
            payload = ex
        if label:
            parts.append(f"_{label}_:")
            parts.append("")
        rendered = yaml.safe_dump(
            payload, sort_keys=False, default_flow_style=False
        ).rstrip()
        parts.append("```yaml")
        parts.append(rendered)
        parts.append("```")
        parts.append("")
    return "\n".join(parts)


def _render_property_row(
    name: str,
    prop: dict[str, Any],
    *,
    required: bool,
    type_override: str | None = None,
) -> str:
    type_str = type_override or _format_type(prop)
    flag_bits = _flags(prop)
    if required:
        flag_bits.insert(0, _pill("required", kind="required"))

    name_md = f"`{name}`"
    if flag_bits:
        name_md += "<br>" + " ".join(flag_bits)

    desc_block = _build_description_block(prop)

    name_html = _md_to_html(name_md, inline=True)
    type_html = _md_to_html(type_str, inline=True)
    desc_html = _md_to_html(desc_block) or "&mdash;"

    return (
        "<tr>\n"
        f"<td>{name_html}</td>\n"
        f"<td>{type_html}</td>\n"
        f"<td>{desc_html}</td>\n"
        "</tr>"
    )


def _build_description_block(prop: dict[str, Any]) -> str:
    parts: list[str] = []

    desc = (prop.get("description") or "").strip()
    if desc:
        parts.append(_demote_headings(desc, levels=4))
        parts.append("")

    rules: list[str] = []

    enum = prop.get("enum")
    if enum:
        rules.append(
            "- Allowed values: " + ", ".join(f"`{v}`" for v in enum)
        )

    rule_keys: list[tuple[str, str]] = [
        ("Default", "default"),
        ("Min length", "minLength"),
        ("Max length", "maxLength"),
        ("Pattern", "pattern"),
        ("Minimum", "minimum"),
        ("Maximum", "maximum"),
        ("Exclusive minimum", "exclusiveMinimum"),
        ("Exclusive maximum", "exclusiveMaximum"),
        ("Multiple of", "multipleOf"),
        ("Min items", "minItems"),
        ("Max items", "maxItems"),
        ("Unique items", "uniqueItems"),
        ("Min properties", "minProperties"),
        ("Max properties", "maxProperties"),
    ]
    for label, key in rule_keys:
        if key in prop and prop[key] is not None:
            rules.append(f"- {label}: `{prop[key]}`")

    example = prop.get("example")
    if isinstance(example, (str, int, float, bool)):
        rules.append(f"- Example: `{example}`")

    if rules:
        if desc:
            parts.append("**Constraints**")
            parts.append("")
        parts.extend(rules)

    return "\n".join(parts).strip()


def _flatten_properties(
    properties: dict[str, Any],
    required: set[str],
    *,
    hide_internal: bool,
    max_depth: int,
    _prefix: str = "",
    _depth: int = 1,
) -> list[tuple[str, dict[str, Any], bool, str | None]]:
    rows: list[tuple[str, dict[str, Any], bool, str | None]] = []
    for pname, pschema in properties.items():
        if not isinstance(pschema, dict):
            continue
        if hide_internal and pschema.get("x-internal-only") is True:
            continue

        path = f"{_prefix}{pname}"
        req = pname in required
        child_props = pschema.get("properties")
        is_inline_object = (
            "$ref" not in pschema
            and isinstance(child_props, dict) and child_props
        )
        items = pschema.get("items") if pschema.get("type") == "array" else None
        item_props = items.get("properties") if isinstance(items, dict) else None
        is_array_of_objects = (
            isinstance(items, dict) and "$ref" not in items
            and isinstance(item_props, dict) and item_props
        )

        if is_inline_object and _depth < max_depth:
            rows.append((path, pschema, req, None))
            rows.extend(_flatten_properties(
                child_props, set(pschema.get("required") or []),
                hide_internal=hide_internal, max_depth=max_depth,
                _prefix=f"{path}.", _depth=_depth + 1,
            ))
        elif is_array_of_objects and _depth < max_depth:
            rows.append((f"{path}[]", pschema, req, "array of objects"))
            rows.extend(_flatten_properties(
                item_props, set(items.get("required") or []),
                hide_internal=hide_internal, max_depth=max_depth,
                _prefix=f"{path}[].", _depth=_depth + 1,
            ))
        else:
            rows.append((path, pschema, req, None))
    return rows


def _render_properties_table(
    properties: dict[str, Any],
    required: set[str],
    *,
    hide_internal: bool = False,
    max_depth: int = 3,
) -> str:
    rows = _flatten_properties(
        properties, required, hide_internal=hide_internal, max_depth=max_depth,
    )
    if not rows:
        return ""
    parts: list[str] = [
        '<table>',
        '<thead>',
        '<tr><th>Name</th><th>Type</th><th>Description</th></tr>',
        '</thead>',
        '<tbody>',
    ]
    for path, pschema, req, type_override in rows:
        parts.append(_render_property_row(
            path, pschema, required=req, type_override=type_override,
        ))
    parts.append('</tbody>')
    parts.append('</table>')
    parts.append("")
    return "\n".join(parts)


def _render_schema(
    schema: dict[str, Any],
    *,
    hide_internal: bool,
    max_depth: int = 3,
) -> str:
    parts: list[str] = []

    desc = (schema.get("description") or "").strip()
    if desc:
        parts.append(_demote_headings(desc))
        parts.append("")

    if "$ref" in schema:
        parts.append(f"_Type:_ {_ref_link(schema['$ref'])}")
        return "\n".join(parts).strip()

    t = schema.get("type")
    enum = schema.get("enum")

    base_props: dict[str, Any] = dict(schema.get("properties") or {})
    base_required: set[str] = set(schema.get("required") or [])
    compose_lines: list[str] = []

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        includes: list[str] = []
        for mem in all_of:
            if not isinstance(mem, dict):
                continue
            if "$ref" in mem:
                includes.append(_ref_link(mem["$ref"]))
            else:
                base_props.update(mem.get("properties") or {})
                base_required.update(mem.get("required") or [])
        if includes:
            compose_lines.append("**All of:** " + " | ".join(includes))

    for kw, label in (("oneOf", "One of"), ("anyOf", "Any of")):
        members = schema.get(kw)
        if isinstance(members, list) and members:
            rendered: list[str] = []
            for mem in members:
                if isinstance(mem, dict) and "$ref" in mem:
                    rendered.append(_ref_link(mem["$ref"]))
                elif isinstance(mem, dict):
                    rendered.append(f"`{_format_type(mem)}`")
                else:
                    rendered.append(f"`{mem}`")
            compose_lines.append(f"**{label}:** " + " | ".join(rendered))

    if enum and not base_props:
        if t:
            parts.append(f"_Type:_ `{t}`")
            parts.append("")
        parts.append("**Allowed values:**")
        parts.append("")
        for v in enum:
            parts.append(f"- `{v}`")
        return "\n".join(parts).strip()

    if t:
        parts.append(f"_Type:_ `{t}`")
        parts.append("")

    for line in compose_lines:
        parts.append(line)
        parts.append("")

    if base_props:
        parts.append("_Properties:_")
        parts.append("")
        parts.append(_render_properties_table(
            base_props, base_required,
            hide_internal=hide_internal, max_depth=max_depth,
        ))

    return "\n".join(parts).strip()


def _render_security_inline(spec: dict[str, Any], entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""

    scopes: Any = None
    if "$ref" in entry:
        ref = entry["$ref"]
        scheme_name = ref.rsplit("/", 1)[-1]
        scheme = _resolve_ref(spec, ref)
    else:
        items = list(entry.items())
        if not items:
            return ""
        scheme_name, scopes = items[0]
        components = (spec.get("components") or {}).get("securitySchemes") or {}
        scheme = components.get(scheme_name) if isinstance(components, dict) else None

    if not isinstance(scheme, dict):
        return f"- **Security:** `{scheme_name}`"

    body_lines: list[str] = []
    t = scheme.get("type")
    if t:
        body_lines.append(f"**Type:** {_pill(str(t), kind='scheme')}")
        body_lines.append("")
    for label, key in (
        ("Name", "name"),
        ("In", "in"),
        ("Scheme", "scheme"),
        ("Bearer format", "bearerFormat"),
        ("OpenID Connect URL", "openIdConnectUrl"),
    ):
        v = scheme.get(key)
        if v:
            body_lines.append(f"**{label}:** `{v}`")
    sdesc = (scheme.get("description") or "").strip()
    if sdesc:
        if body_lines and body_lines[-1] != "":
            body_lines.append("")
        body_lines.append(_demote_headings(sdesc, levels=2))

    if isinstance(scopes, list) and scopes:
        if body_lines and body_lines[-1] != "":
            body_lines.append("")
        body_lines.append("**Scopes:** " + ", ".join(f"`{sc}`" for sc in scopes))

    indented = "\n".join(("    " + l) if l else "" for l in body_lines)

    return (
        f'!!! note ":material-security: Security: {scheme_name}"\n'
        f"{indented}"
    )


def _render_downloads_table(
    spec_url: str,
    attachments: list[dict[str, Any]],
    *,
    hide_download: bool,
) -> str:
    rows: list[str] = []
    if spec_url and not hide_download:
        rows.append(f":material-file-document: [Specification Source]({spec_url})")
    for att in attachments:
        if att.get("url"):
            rows.append(f":material-file-document: [{att['title']}]({att['url']})")
        else:
            rows.append(f":material-file-document: {att['title']} _(unavailable: {att.get('error')})_")

    if not rows:
        return ""

    out = ["| Downloads |", "|---|"]
    out.extend(f"| {r} |" for r in rows)
    out.append("")
    return "\n".join(out)


def _error_page(title: str, detail: str) -> str:
    return (
        "# AsyncAPI page failed to render\n\n"
        f'!!! danger "{title}"\n'
        f"    {detail}\n"
    )
