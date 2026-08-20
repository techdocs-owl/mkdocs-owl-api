"""
Markdown and HTML plumbing shared by every renderer.

Nothing here knows what a spec is: these take strings and values and hand back
markup.
"""

from __future__ import annotations

import html as _html
import re
from typing import Any, Iterable, Sequence

import markdown as _md

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
#: A bullet or numbered list item, at any indent.
_LIST_ITEM_RE = re.compile(r"^[ \t]*([-*+]\s+|\d+[.)]\s+)")


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


def _html_table(rows: "Iterable[str]", *, headers: "Sequence[str] | None" = None) -> str:
    """
    Wrap pre-rendered `<tr>` cells in a table. Built as HTML rather than a
    markdown pipe table because the cells carry block content - constraint
    lists, admonition-free multi-line descriptions - that pipe tables cannot
    hold.
    """
    out = ["<table>"]
    if headers:
        out += [
            "<thead>",
            "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>",
            "</thead>",
        ]
    out.append("<tbody>")
    out.extend(rows)
    out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out)


def _html_list(items: "Iterable[str]", *, kind: str) -> str:
    """
    Wrap pre-rendered item bodies in a `<ul>`.
    """
    body = "\n".join(f"<li>{item}</li>" for item in items)
    if not body:
        return ""
    return f'<ul class="techdocs-owl-api-{kind}">\n{body}\n</ul>'


def _table_cell(text: Any) -> str:
    """Flatten arbitrary (user-supplied) text so it can't break out of a table cell."""
    return " ".join(str(text or "").split()).replace("|", "\\|")


def _file_format(url: str) -> str:
    """The format label for a download, taken from its file extension."""
    filename = url.split("?")[0].rsplit("/", 1)[-1]
    return filename.rpartition(".")[2].lower() or "unknown"
