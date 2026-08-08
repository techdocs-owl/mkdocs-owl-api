"""
Reader for JSON Schema nodes, across every dialect the plugin accepts.

`$ref` is read as a keyword, so a node carrying one is an ordinary schema that
happens to reference another. 2020-12 applies it in place, alongside its
siblings; earlier drafts say it replaces the object and the siblings are
ignored - but an author who wrote one meant it, so they are kept.

Unmodelled keywords - `xml`, `if`/`then`/`else`, `$schema` - are dropped in
silence. Warnings are for a keyword that is modelled but unusable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..common.doc_parser import read_external_docs
from ..common.parse_report import Reporter
from ..common.parse_util import (
    extensions_of,
    is_mapping,
    kind_of,
    read_bool,
    read_int,
    read_list,
    read_mapping,
    read_number,
    read_str,
    read_str_map,
    read_str_tuple,
)
from .schema_model import (
    UNSET,
    ArrayConstraints,
    Discriminator,
    NumericConstraints,
    ObjectConstraints,
    Schema,
    StringConstraints,
)

#: Extensions promoted to a modelled field, so not repeated as extras.
_CONSUMED_EXTENSIONS = frozenset({"x-nullable"})

#: The constraint group each declared type admits. A type absent from this map -
#: `boolean` and `null` - admits none, and a schema declaring no type at all
#: admits every group, since its keywords still assert on matching instances.
_CONSTRAINTS_BY_TYPE = {
    "string": "string",
    "number": "numeric",
    "integer": "numeric",
    "array": "array",
    "object": "object",
}


def read_schema(raw: Any, report: Reporter) -> Schema | None:
    """Read one schema node. `None` means the node was unusable."""
    if isinstance(raw, bool):
        # 2020-12 boolean schemas: `true` accepts every instance, `false` none.
        return Schema() if raw else Schema(not_=Schema())
    if not is_mapping(raw):
        report.warn(f"expected an object, found {kind_of(raw)}")
        return None
    return _read_object(raw, report)


def _ref_name(pointer: str) -> str:
    """
    The component name a pointer ends in.

    `#/definitions/Pet` and `#/components/schemas/Pet` both give `Pet`, so two
    documents that keep their components in different places still agree on
    what a reference identifies.
    """
    return pointer.rsplit("/", 1)[-1] if "/" in pointer else pointer


def _read_types(raw: Mapping[str, Any], report: Reporter) -> tuple[tuple[str, ...], bool]:
    """The declared types with `null` split off into a nullability flag."""
    declared = raw.get("type")
    types: tuple[str, ...] = ()
    nullable = False

    if isinstance(declared, str):
        types = (declared,)
    elif isinstance(declared, list):
        kept: list[str] = []
        for index, item in enumerate(declared):
            if isinstance(item, str):
                kept.append(item)
            else:
                report.at("type", index).warn(
                    f"expected a string, found {kind_of(item)}"
                )
        nullable = "null" in kept
        types = tuple(name for name in kept if name != "null")
    elif declared is not None:
        report.at("type").warn(
            f"expected a string or array, found {kind_of(declared)}"
        )

    # None of the three spellings asserts non-nullability, so they OR together.
    for key in ("nullable", "x-nullable"):
        if read_bool(raw, key, report):
            nullable = True

    return types, nullable


def _read_limit(
    raw: Mapping[str, Any], limit_key: str, exclusive_key: str, report: Reporter,
) -> tuple[float | int | None, float | int | None]:
    """
    One inclusive limit and one exclusive limit, from either spelling.

    Draft-4 puts a boolean in `exclusiveMinimum` that modifies `minimum`, and
    requires `minimum` alongside it. 2020-12 makes the two independent keywords,
    both taking a number, either or both of which a schema may state. The
    spellings are different JSON types, so nothing needs to be told which is in
    use - but `bool` is a subclass of `int` in Python, so it is tested first.
    """
    limit = read_number(raw, limit_key, report)
    exclusive = raw.get(exclusive_key)

    if isinstance(exclusive, bool):
        if limit is None:
            if exclusive:
                report.at(exclusive_key).warn(
                    f"boolean form needs `{limit_key}` alongside it"
                )
            return None, None
        return (None, limit) if exclusive else (limit, None)

    if isinstance(exclusive, (int, float)):
        return limit, exclusive

    if exclusive is not None:
        report.at(exclusive_key).warn(
            f"expected a number or boolean, found {kind_of(exclusive)}"
        )
    return limit, None


def _read_string_constraints(
    raw: Mapping[str, Any], report: Reporter,
) -> StringConstraints | None:
    constraints = StringConstraints(
        min_length=read_int(raw, "minLength", report),
        max_length=read_int(raw, "maxLength", report),
        pattern=read_str(raw, "pattern", report),
    )
    return constraints if constraints != StringConstraints() else None


def _read_numeric_constraints(
    raw: Mapping[str, Any], report: Reporter,
) -> NumericConstraints | None:
    minimum, exclusive_minimum = _read_limit(raw, "minimum", "exclusiveMinimum", report)
    maximum, exclusive_maximum = _read_limit(raw, "maximum", "exclusiveMaximum", report)
    constraints = NumericConstraints(
        minimum=minimum,
        exclusive_minimum=exclusive_minimum,
        maximum=maximum,
        exclusive_maximum=exclusive_maximum,
        multiple_of=read_number(raw, "multipleOf", report),
    )
    return constraints if constraints != NumericConstraints() else None


def _read_array_constraints(
    raw: Mapping[str, Any], report: Reporter,
) -> ArrayConstraints | None:
    constraints = ArrayConstraints(
        min_items=read_int(raw, "minItems", report),
        max_items=read_int(raw, "maxItems", report),
        unique_items=bool(read_bool(raw, "uniqueItems", report)),
    )
    return constraints if constraints != ArrayConstraints() else None


def _read_object_constraints(
    raw: Mapping[str, Any], report: Reporter,
) -> ObjectConstraints | None:
    constraints = ObjectConstraints(
        min_properties=read_int(raw, "minProperties", report),
        max_properties=read_int(raw, "maxProperties", report),
    )
    return constraints if constraints != ObjectConstraints() else None


def _constraint_groups(types: tuple[str, ...]) -> set[str]:
    """
    Which constraint groups a schema's declared types admit.

    A schema that declares no type admits all of them: its keywords still
    assert on instances of the matching type. One that declares a type admits
    only that type's group, and a keyword from any other asserts nothing, so it
    is passed over.
    """
    if not types:
        return set(_CONSTRAINTS_BY_TYPE.values())
    return {
        _CONSTRAINTS_BY_TYPE[name] for name in types if name in _CONSTRAINTS_BY_TYPE
    }


def _read_subschemas(
    raw: Mapping[str, Any], key: str, report: Reporter,
) -> tuple[Schema, ...]:
    items = read_list(raw, key, report)
    if items is None:
        return ()
    read = (read_schema(item, report.at(key, index)) for index, item in enumerate(items))
    return tuple(schema for schema in read if schema is not None)


def _read_properties(
    raw: Mapping[str, Any], report: Reporter,
) -> dict[str, Schema]:
    node = read_mapping(raw, "properties", report)
    if node is None:
        return {}
    properties: dict[str, Schema] = {}
    for name, value in node.items():
        schema = read_schema(value, report.at("properties", name))
        if schema is not None:
            properties[str(name)] = schema
    return properties


def _read_additional_properties(
    raw: Mapping[str, Any], report: Reporter,
) -> bool | Schema | None:
    if "additionalProperties" not in raw:
        return None
    value = raw["additionalProperties"]
    if isinstance(value, bool):
        return value
    return read_schema(value, report.at("additionalProperties"))


def _read_items(
    raw: Mapping[str, Any], report: Reporter,
) -> tuple[Schema | None, tuple[Schema, ...]]:
    """
    The item schemas, in either the draft-4/07 or the 2020-12 spelling.

    An array-valued `items` is tuple validation, and its companion
    `additionalItems` is what 2020-12 calls `items`. An explicit `prefixItems`
    is newer, so it wins.
    """
    items: Schema | None = None
    prefix: tuple[Schema, ...] = ()

    raw_items = raw.get("items")
    if isinstance(raw_items, list):
        prefix = _read_subschemas(raw, "items", report)
        if "additionalItems" in raw:
            items = read_schema(raw["additionalItems"], report.at("additionalItems"))
    elif raw_items is not None:
        items = read_schema(raw_items, report.at("items"))

    if "prefixItems" in raw:
        prefix = _read_subschemas(raw, "prefixItems", report)

    return items, prefix


def _read_discriminator(
    raw: Mapping[str, Any], report: Reporter,
) -> Discriminator | None:
    """Either a bare property name, or an object that may also carry a mapping."""
    value = raw.get("discriminator")
    if value is None:
        return None
    if isinstance(value, str):
        return Discriminator(property_name=value)
    if is_mapping(value):
        name = read_str(value, "propertyName", report.at("discriminator"))
        if not name:
            report.at("discriminator").warn("no `propertyName`")
            return None
        return Discriminator(
            property_name=name,
            mapping=read_str_map(value, "mapping", report.at("discriminator")),
        )
    report.at("discriminator").warn(
        f"expected a string or object, found {kind_of(value)}"
    )
    return None


def _read_examples(raw: Mapping[str, Any], report: Reporter) -> tuple[Any, ...]:
    """`examples` is the array form; `example` a single value."""
    if "examples" in raw:
        items = read_list(raw, "examples", report)
        if items is not None:
            return tuple(items)
    if "example" in raw:
        return (raw["example"],)
    return ()


def _read_object(raw: Mapping[str, Any], report: Reporter) -> Schema:
    """Every modelled keyword of a schema object."""
    ref = read_str(raw, "$ref", report)
    types, nullable = _read_types(raw, report)
    groups = _constraint_groups(types)
    items, prefix_items = _read_items(raw, report)

    format_ = read_str(raw, "format", report)
    if types == ("file",):
        # `file` is not a JSON Schema type. Where it appears it marks an
        # upload or download, which is a binary string.
        types, format_ = ("string",), format_ or "binary"

    return Schema(
        ref=ref,
        ref_name=_ref_name(ref) if ref is not None else None,

        title=read_str(raw, "title", report),
        description=read_str(raw, "description", report),
        default=raw["default"] if "default" in raw else UNSET,
        examples=_read_examples(raw, report),
        deprecated=bool(read_bool(raw, "deprecated", report)),
        read_only=bool(read_bool(raw, "readOnly", report)),
        write_only=bool(read_bool(raw, "writeOnly", report)),

        types=types,
        nullable=nullable,
        format=format_,
        enum=tuple(read_list(raw, "enum", report) or ()),
        const=raw["const"] if "const" in raw else UNSET,

        properties=_read_properties(raw, report),
        required=read_str_tuple(raw, "required", report),
        additional_properties=_read_additional_properties(raw, report),

        items=items,
        prefix_items=prefix_items,

        string_constraints=(
            _read_string_constraints(raw, report) if "string" in groups else None
        ),
        numeric_constraints=(
            _read_numeric_constraints(raw, report) if "numeric" in groups else None
        ),
        array_constraints=(
            _read_array_constraints(raw, report) if "array" in groups else None
        ),
        object_constraints=(
            _read_object_constraints(raw, report) if "object" in groups else None
        ),

        all_of=_read_subschemas(raw, "allOf", report),
        any_of=_read_subschemas(raw, "anyOf", report),
        one_of=_read_subschemas(raw, "oneOf", report),
        not_=read_schema(raw["not"], report.at("not")) if "not" in raw else None,

        discriminator=_read_discriminator(raw, report),
        external_docs=read_external_docs(
            raw.get("externalDocs"), report.at("externalDocs"),
        ),
        extensions=extensions_of(raw, consumed=_CONSUMED_EXTENSIONS),
    )
