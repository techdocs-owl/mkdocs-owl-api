"""
Schema model in, page blocks out.

Property tables are flattened rather than nested: a child property becomes a row
of its own keyed by the dotted path to it, so one table shows a whole object.

Tables are hand-built HTML because their cells carry block content - a
description, a constraints list, a dimmed note - which a pipe table cannot hold.
"""

from __future__ import annotations

from dataclasses import dataclass

from .primitives import (
    _anchor,
    _demote_headings,
    _html_table,
    _infer_enum_type,
    _md_to_html,
    _pill,
    _property_name_html,
)
from .schema_model import UNSET, Schema

#: Section a schema reference points into.
_SCHEMAS = "schemas"

#: Vendor extension marking a property as not for publication.
_INTERNAL = "x-internal-only"

PROPERTY_HEADERS = ("Name", "Type", "Description")


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
        flags.append(_pill("required", kind="required"))
    if schema.extensions.get(_INTERNAL) is True:
        flags.append(_pill("internal", kind="internal"))
    if schema.deprecated:
        flags.append(_pill("deprecated", kind="deprecated"))
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


def _composition(schema: Schema) -> tuple[list[str], dict[str, Schema], set[str]]:
    """
    The composition lines, plus the properties an inline `allOf` member folds in.

    A referenced member is named and linked; an inline one is merged, because
    its properties belong to the same object and a reader wants one table.
    """
    lines: list[str] = []
    properties = dict(schema.properties)
    required = set(schema.required)

    includes: list[str] = []
    for member in schema.all_of:
        if member.is_ref():
            includes.append(ref_link(member))
        else:
            properties.update(member.properties)
            required.update(member.required)
    if includes:
        lines.append("**All of:** " + " | ".join(includes))

    for members, label in ((schema.one_of, "One of"), (schema.any_of, "Any of")):
        if members:
            lines.append(f"**{label}:** " + " | ".join(
                ref_link(m) if m.is_ref() else f"`{format_type(m)}`" for m in members
            ))

    return lines, properties, required


def render_schema(
    schema: Schema, *, hide_internal: bool = False, max_depth: int = 1,
) -> list[str]:
    """One named schema: description, type, composition, property table."""
    blocks: list[str] = []

    description = (schema.description or "").strip()
    if description:
        blocks.append(_demote_headings(description))

    if schema.is_ref():
        blocks.append(f"_Type:_ {ref_link(schema)}")
        return blocks

    note = closed_object_note(schema)
    if note:
        blocks.append(note)

    type_name = " | ".join(schema.types) or _infer_enum_type(list(schema.enum))
    composition, properties, required = _composition(schema)

    if schema.enum and not properties:
        if type_name:
            blocks.append(f"_Type:_ `{type_name}`")
        blocks.append("**Allowed values:**")
        blocks.append("\n".join(f"- `{value}`" for value in schema.enum))
        return blocks

    if type_name:
        blocks.append(f"_Type:_ `{type_name}`")
    blocks.extend(composition)

    if properties:
        blocks.append("_Properties:_")
        merged = Schema(properties=properties, required=tuple(sorted(required)))
        blocks.extend(property_table(property_rows(
            merged, hide_internal=hide_internal, max_depth=max_depth,
        )))

    return blocks
