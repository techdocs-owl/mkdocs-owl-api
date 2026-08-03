"""
Shared rendering building blocks used by both the AsyncAPI and OpenAPI page renderers.
"""

from __future__ import annotations

import html as _html
import re
from typing import Any, Iterable, Sequence

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


_JSON_TYPE_NAMES: list[tuple[type, str]] = [
    (bool, "boolean"),  # before int - bool is an int subclass
    (int, "integer"),
    (float, "number"),
    (str, "string"),
    (list, "array"),
    (dict, "object"),
]


def _infer_enum_type(enum: Any) -> str | None:
    """
    An `enum` without a sibling `type` still has an obvious type - the one its
    values share. Returns None when the values disagree or aren't recognisable.
    """
    if not isinstance(enum, list) or not enum:
        return None

    names: set[str] = set()
    for value in enum:
        if value is None:
            names.add("null")
            continue
        for py_type, name in _JSON_TYPE_NAMES:
            if isinstance(value, py_type):
                names.add(name)
                break
        else:
            return None

    if not names:
        return None
    return " | ".join(sorted(names))


def _format_type(prop: Any) -> str:
    """
    Render a property's type as a short, readable expression.
    """
    if not isinstance(prop, dict):
        return "any"

    if "$ref" in prop:
        return _ref_link(prop["$ref"])

    # A lone `allOf` member is the usual way to attach a description to a `$ref`
    # - the value conforms to that member, so it takes the member's type.
    all_of = prop.get("allOf")
    if isinstance(all_of, list) and len(all_of) == 1 and not prop.get("type"):
        return _format_type(all_of[0])

    t = prop.get("type")
    if isinstance(t, list):
        t = " | ".join(str(x) for x in t)
    if not t:
        t = _infer_enum_type(prop.get("enum"))
    fmt = prop.get("format")

    if t == "object" and "additionalProperties" in prop:
        # Doubles as a value schema and as a bool toggle for extra keys - only
        # the schema form (and a bare `true`) describes a map.
        extra = prop["additionalProperties"]
        if isinstance(extra, dict):
            return f"map of string → {_format_type(extra)}"
        if extra is True:
            return "map of string → any"
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


def _property_name_html(path: str) -> str:
    """
    Render a flattened dot-path as plain text - ancestors dimmed, leaf bold -
    so the leaf name stays legible at depth. The path is kept contiguous so
    in-page search for the full `a.b.c` still matches.
    """
    prefix, sep, leaf = path.rpartition(".")
    leaf_html = f'<span class="techdocs-owl-api-prop">{_html.escape(leaf)}</span>'
    if not sep:
        return leaf_html
    # `<wbr>` after each dot: a break *opportunity*, so long paths wrap on
    # segment boundaries instead of forcing the column wide. It contributes no
    # characters, so the copied/searched text stays the plain path.
    prefix_html = _html.escape(prefix + sep).replace(".", ".<wbr>")
    return (
        f'<span class="techdocs-owl-api-path">{prefix_html}</span>'
        f"{leaf_html}"
    )


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

    # Built as HTML rather than markdown: the path needs per-segment styling
    # that inline markdown can't express.
    name_html = _property_name_html(name)
    if flag_bits:
        name_html += "<br>" + " ".join(flag_bits)

    desc_block = _build_description_block(prop)

    type_html = _md_to_html(type_str, inline=True)
    desc_html = _md_to_html(desc_block) or "&mdash;"

    return (
        "<tr>\n"
        f"<td>{name_html}</td>\n"
        f"<td>{type_html}</td>\n"
        f"<td>{desc_html}</td>\n"
        "</tr>"
    )


def _closed_object_note(schema: dict[str, Any]) -> str:
    """
    `additionalProperties: false` closes the object to unlisted keys - worth
    stating outright, but as a dimmed aside rather than a constraint bullet.
    """
    if schema.get("additionalProperties") is not False:
        return ""
    return (
        '<span class="techdocs-owl-api-note">'
        "Additional properties are NOT allowed."
        "</span>"
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

    note = _closed_object_note(prop)
    if note:
        if parts:
            parts.append("")
        parts.append(note)

    return "\n".join(parts).strip()


def _html_table(headers: "Sequence[str]", rows: "Iterable[str]") -> str:
    """
    Wrap pre-rendered `<tr>` cells in a table. Built as HTML rather than a
    markdown pipe table because the cells carry block content - constraint
    lists, admonition-free multi-line descriptions - that pipe tables cannot
    hold.
    """
    out = [
        "<table>",
        "<thead>",
        "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>",
        "</thead>",
        "<tbody>",
    ]
    out.extend(rows)
    out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out)


def _table_cell(text: Any) -> str:
    """Flatten arbitrary (user-supplied) text so it can't break out of a table cell."""
    return " ".join(str(text or "").split()).replace("|", "\\|")


def _file_format(url: str) -> str:
    """The format label for a download, taken from its file extension."""
    filename = url.split("?")[0].rsplit("/", 1)[-1]
    return filename.rpartition(".")[2].lower() or "unknown"
