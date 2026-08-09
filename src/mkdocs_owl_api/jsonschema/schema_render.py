"""
Schema model in, page blocks out.

Property tables are flattened rather than nested: a child property becomes a row
of its own keyed by the dotted path to it, so one table shows a whole object.

Tables are hand-built HTML because their cells carry block content - a
description, a constraints list, a dimmed note - which a pipe table cannot hold.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..common.primitives.markup import (
    _anchor,
    _demote_headings,
    _html_list,
    _html_table,
    _infer_enum_type,
    _md_to_html,
    _property_name_html,
)
from ..common.primitives.pills import (
    deprecated_pill,
    internal_pill,
    pill_blue,
    pill_green,
    pill_grey,
    pill_indigo,
    pill_orange,
    pill_purple,
    required_pill,
)
from .schema_model import UNSET, Schema, SchemaShape

#: Section a schema reference points into.
_SCHEMAS = "schemas"

#: How far composition alternatives nest before the renderer stops listing
#: Hardcoded at the moment.
_MAX_ALTERNATIVE_DEPTH = 3

#: Vendor extension marking a property as not for publication.
_INTERNAL = "x-internal-only"

PROPERTY_HEADERS = ("Name", "Type", "Description")


_SCHEMA_SHAPE_PILLS = {
    SchemaShape.REF: pill_green,
    SchemaShape.OBJECT: pill_blue,
    SchemaShape.ARRAY: pill_orange,
    SchemaShape.COMPOSITION: pill_purple,
    SchemaShape.PRIMITIVE: pill_indigo,
}

def _type_name(schema: Schema) -> str:
    # `format_type` falls back to a bare "object" for a schema that states no
    # type of its own, which says nothing the shape pill has not said already.
    name = format_type(schema)
    return "" if name == "object" else name


def _schema_shape_text(schema: Schema) -> str:
    schema_shape = schema.schema_shape()
    shape_pill = _SCHEMA_SHAPE_PILLS.get(schema_shape, pill_grey)(schema_shape.value.upper())
    name = _type_name(schema)
    if not name:
        return shape_pill
    # A reference is already a link, so it is not fenced as code.
    if schema_shape is SchemaShape.REF:
        return f"{shape_pill} {name}"
    return f"{shape_pill} `{name}`"


def ref_link(schema: Schema) -> str:
    """
    A link to where the referenced schema is rendered.

    Built from `ref_name` rather than the pointer, so a reference resolves to
    the same anchor whichever way its document spells the path to components.
    """
    name = schema.ref_name or ""
    if not name:
        return "`<broken-ref>`"
    return f"[`{name}`](#{_anchor(_SCHEMAS, name)})"


def format_type(schema: Schema | None) -> str:
    """A short, readable type expression."""
    if schema is None:
        return "any"
    if schema.is_ref():
        return ref_link(schema)

    # A lone `allOf` member is how a document attaches keywords to a reference
    # without stating a type; the value conforms to that member.
    if len(schema.all_of) == 1 and not schema.types:
        return format_type(schema.all_of[0])

    name = " | ".join(schema.types)
    if not name:
        name = _infer_enum_type(list(schema.enum)) or ""

    if "object" in schema.types and schema.additional_properties is not None:
        extra = schema.additional_properties
        if isinstance(extra, Schema):
            name = f"map of string → {format_type(extra)}"
        elif extra is True:
            name = "map of string → any"
    elif "array" in schema.types:
        name = f"array of {format_type(schema.items)}"
    elif name and schema.format:
        name = f"{name} ({schema.format})"

    if not name:
        name = "object"
    return f"{name} | null" if schema.nullable else name


def closed_object_note(schema: Schema) -> str:
    """
    `additionalProperties: false` closes the object to unlisted keys - worth
    stating outright, but as a dimmed aside rather than a constraint bullet.
    """
    if schema.additional_properties is not False:
        return ""
    return (
        '<span class="techdocs-owl-api-note">'
        "Additional properties are NOT allowed."
        "</span>"
    )


def _constraint_rules(schema: Schema) -> list[str]:
    """The constraint bullets, in a fixed order regardless of source order."""
    rules: list[str] = []

    if schema.enum:
        rules.append("- Allowed values: " + ", ".join(f"`{v}`" for v in schema.enum))
    if schema.default is not UNSET:
        rules.append(f"- Default: `{schema.default}`")
    if schema.const is not UNSET:
        rules.append(f"- Constant: `{schema.const}`")

    labelled: list[tuple[str, object]] = []
    if schema.string_constraints is not None:
        text = schema.string_constraints
        labelled += [("Min length", text.min_length),
                     ("Max length", text.max_length),
                     ("Pattern", text.pattern)]
    if schema.numeric_constraints is not None:
        number = schema.numeric_constraints
        labelled += [("Minimum", number.minimum),
                     ("Maximum", number.maximum),
                     ("Exclusive minimum", number.exclusive_minimum),
                     ("Exclusive maximum", number.exclusive_maximum),
                     ("Multiple of", number.multiple_of)]
    if schema.array_constraints is not None:
        array = schema.array_constraints
        labelled += [("Min items", array.min_items),
                     ("Max items", array.max_items),
                     ("Unique items", array.unique_items or None)]
    if schema.object_constraints is not None:
        obj = schema.object_constraints
        labelled += [("Min properties", obj.min_properties),
                     ("Max properties", obj.max_properties)]

    rules += [f"- {label}: `{value}`" for label, value in labelled if value is not None]

    for example in schema.examples:
        if isinstance(example, (str, int, float, bool)):
            rules.append(f"- Example: `{example}`")
            break
    return rules


def describe(schema: Schema) -> str:
    """A property's description cell: prose, then what constrains it."""
    parts: list[str] = []

    description = (schema.description or "").strip()
    if description:
        parts.append(_demote_headings(description, levels=4))
        parts.append("")

    rules = _constraint_rules(schema)
    if rules:
        if description:
            parts.append("**Constraints**")
            parts.append("")
        parts.extend(rules)

    note = closed_object_note(schema)
    if note:
        if parts:
            parts.append("")
        parts.append(note)

    return "\n".join(parts).strip()


@dataclass(frozen=True)
class PropertyRow:
    """One line of a property table, already flattened out of the tree."""

    path: str
    schema: Schema
    required: bool
    type_override: str | None = None


def _is_expandable_object(schema: Schema) -> bool:
    return not schema.is_ref() and bool(schema.properties)


def property_rows(
    schema: Schema, *, hide_internal: bool = False, max_depth: int = 1,
) -> list[PropertyRow]:
    """
    A schema's properties, flattened depth-first into dotted paths.

    A referenced schema is never expanded - it is rendered under its own
    heading, and the row links there instead.
    """
    def walk_properties(schema: Schema, prefix: str, depth: int) -> list[PropertyRow]:
        rows: list[PropertyRow] = []
        for name, child in schema.properties.items():
            if hide_internal and child.extensions.get(_INTERNAL) is True:
                continue

            path = f"{prefix}{name}"
            required = schema.is_property_required(name)
            items = child.items if "array" in child.types else None

            if _is_expandable_object(child) and depth < max_depth:
                rows.append(PropertyRow(path, child, required))
                rows.extend(walk_properties(child, f"{path}.", depth + 1))
            elif (items is not None and _is_expandable_object(items)
                    and depth < max_depth):
                rows.append(PropertyRow(f"{path}[]", child, required,
                                        "array of objects"))
                rows.extend(walk_properties(items, f"{path}[].", depth + 1))
            else:
                rows.append(PropertyRow(path, child, required))
        return rows

    if not schema.properties:
        return []
    return walk_properties(schema, "", 1)


def _flags(schema: Schema, *, required: bool) -> list[str]:
    flags: list[str] = []
    if required:
        flags.append(required_pill())
    if schema.extensions.get(_INTERNAL) is True:
        flags.append(internal_pill())
    if schema.deprecated:
        flags.append(deprecated_pill())
    return flags


def render_property_row(row: PropertyRow) -> str:
    name_html = _property_name_html(row.path)
    flags = _flags(row.schema, required=row.required)
    if flags:
        name_html += "<br>" + " ".join(flags)

    type_html = _md_to_html(row.type_override or format_type(row.schema), inline=True)
    description_html = _md_to_html(describe(row.schema)) or "&mdash;"

    return (
        "<tr>\n"
        f"<td>{name_html}</td>\n"
        f"<td>{type_html}</td>\n"
        f"<td>{description_html}</td>\n"
        "</tr>"
    )


def property_table(rows: list[PropertyRow]) -> list[str]:
    if not rows:
        return []
    return [_html_table(PROPERTY_HEADERS, [render_property_row(r) for r in rows])]


def _is_renderable(member: Schema) -> bool:
    """
    Whether a composition member has anything to show.
    """
    return member != Schema()


def _composition_alternative(
    member: Schema, *, hide_internal: bool, max_depth: int, depth: int,
) -> str:
    """
    One member of a composition, as the body of an `<li>`.
    """
    parts = [_md_to_html(
        ref_link(member) if member.is_ref() else f"`{format_type(member)}`",
        inline=True,
    )]

    if member.is_ref():
        described = (member.description or "").strip()
        if described:
            parts.append(_md_to_html(described))
        return "\n".join(parts)

    described = describe(member)
    if described:
        parts.append(_md_to_html(described))

    nested = _composition_alternatives(
        member, hide_internal=hide_internal, max_depth=max_depth, depth=depth,
    )
    parts.extend(nested)
    if member.properties:
        parts.extend(property_table(property_rows(
            member, hide_internal=hide_internal, max_depth=max_depth,
        )))

    return "\n".join(parts)


def _members(schema: Schema) -> list[tuple[tuple[Schema, ...], str]]:
    return [(schema.all_of, "All of"),
            (schema.one_of, "One of"),
            (schema.any_of, "Any of")]


def _composition_alternatives(
    schema: Schema, *, hide_internal: bool, max_depth: int, depth: int = 0,
) -> list[str]:
    if depth >= _MAX_ALTERNATIVE_DEPTH or _all_bare_refs(schema):
        lines = _composition_alternatives_line(schema)
        return [_md_to_html(line) for line in lines] if depth else lines

    blocks: list[str] = []
    for members, label in _members(schema):
        shown = [m for m in members if _is_renderable(m)]
        if not shown:
            continue
        items = [
            _composition_alternative(member, hide_internal=hide_internal,
                                     max_depth=max_depth, depth=depth + 1)
            for member in shown
        ]
        blocks.append(f"<p><strong>{label}:</strong></p>")
        blocks.append(_html_list(items, kind="alternatives"))
    return blocks


def _all_bare_refs(schema: Schema) -> bool:
    """
    Whether every member is a reference carrying nothing of its own.
    """
    members = [m for members, _ in _members(schema) for m in members
               if _is_renderable(m)]
    return bool(members) and all(
        m.is_ref() and not (m.description or "").strip() for m in members
    )


def _composition_alternatives_line(schema: Schema) -> list[str]:
    """
    The members named on one line, with nothing said about each.
    """
    lines: list[str] = []
    for members, label in _members(schema):
        shown = [m for m in members if _is_renderable(m)]
        if shown:
            lines.append(f"**{label}:** " + " | ".join(
                ref_link(m) if m.is_ref() else f"`{format_type(m)}`" for m in shown
            ))
    return lines


def _required_composition_alternatives(schema: Schema) -> list[str]:
    """
    Composition constraint.
    """
    lines: list[str] = []
    for members, word in ((schema.one_of, "exactly one"),
                          (schema.any_of, "at least one")):
        if not members or not _is_required_only(members):
            continue
        groups = [", ".join(f"`{name}`" for name in m.required) for m in members]
        lines.append(f"**Requires {word} of:** " + " | ".join(groups))
    return lines


def _is_required_only(members: tuple[Schema, ...]) -> bool:
    return bool(members) and all(
        m.required and not (m.types or m.properties or m.items or m.is_ref()
                            or m.enum or m.all_of or m.any_of or m.one_of)
        for m in members
    )


def _composition_constraint(
    schema: Schema, *, hide_internal: bool, max_depth: int,
) -> list[str]:
    if _required_composition_alternatives(schema):
        return []
    if any(_is_renderable(m) and not m.is_ref()
           for members, _ in _members(schema) for m in members):
        return _composition_alternatives(
            schema, hide_internal=hide_internal, max_depth=max_depth,
        )
    return _composition_alternatives_line(schema)


def _constraints_block(schema: Schema) -> list[str]:
    rules = _constraint_rules(schema)
    return ["\n".join(rules)] if rules else []


def _closed_note(schema: Schema) -> list[str]:
    note = closed_object_note(schema)
    return [note] if note else []


def _render_ref(schema: Schema, **_) -> list[str]:
    return _constraints_block(schema)


def _render_object(schema: Schema, *, hide_internal: bool, max_depth: int) -> list[str]:
    rows = property_rows(schema, hide_internal=hide_internal, max_depth=max_depth)
    return (
            _closed_note(schema)
            + _constraints_block(schema)
            + _required_composition_alternatives(schema)
            + _composition_constraint(schema, hide_internal=hide_internal, max_depth=max_depth)
            + (["_Properties:_", *property_table(rows)] if rows else [])
    )


def _render_array(schema: Schema, *, hide_internal: bool, max_depth: int) -> list[str]:
    blocks = (_constraints_block(schema)
              + _composition_constraint(schema, hide_internal=hide_internal, max_depth=max_depth))
    items = schema.items
    if items is not None and not items.is_ref() and items.properties:
        blocks.append("_Items:_")
        blocks.extend(property_table(property_rows(
            items, hide_internal=hide_internal, max_depth=max_depth,
        )))
    return blocks


def _render_composition(schema: Schema, *, hide_internal: bool, max_depth: int) -> list[str]:
    blocks = _constraints_block(schema)
    return blocks + _required_composition_alternatives(schema) + _composition_alternatives(
        schema, hide_internal=hide_internal, max_depth=max_depth,
    )


def _render_primitive(schema: Schema, **_) -> list[str]:
    return _constraints_block(schema)


_BY_SHAPE = {
    SchemaShape.REF: _render_ref,
    SchemaShape.OBJECT: _render_object,
    SchemaShape.ARRAY: _render_array,
    SchemaShape.COMPOSITION: _render_composition,
    SchemaShape.PRIMITIVE: _render_primitive,
}


def render_schema(
    schema: Schema, *, hide_internal: bool = False, max_depth: int = 1,
) -> list[str]:
    body = _BY_SHAPE[schema.schema_shape()](
        schema, hide_internal=hide_internal, max_depth=max_depth,
    )
    description = (schema.description or "").strip()

    # A caller decides whether to emit its heading by whether this returned
    # anything. The head counts: a `$ref` or an array of primitives carries all
    # of its meaning there and has no body at all.
    if not body and not description and not _type_name(schema):
        return []

    head = _schema_shape_text(schema)
    if description:
        head = f"{head} {_demote_headings(description)}"
    return [head, *body]
