"""
JSON Schema model, normalised onto the 2020-12 vocabulary.

A `$ref` is a keyword like any other, not a separate kind of node: 2020-12
applies it in place, alongside whatever else the node declares.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..common.doc_model import ExternalDocs


class SchemaShape(Enum):
    REF = "ref"
    OBJECT = "object"
    ARRAY = "array"
    COMPOSITION = "composition"
    PRIMITIVE = "primitive"


class _Unset:
    """Type of the `UNSET` sentinel."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


#: Distinguishes "keyword absent" from "present with value `null`". `{"default":
#: null}` means the default *is* null, which `None` alone cannot express.
UNSET: Any = _Unset()


@dataclass(frozen=True)
class StringConstraints:
    """
    Assertions that apply to a string instance.
    """

    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None


@dataclass(frozen=True)
class NumericConstraints:
    """
    Assertions that apply to a number or integer instance.
    """

    minimum: float | None = None
    exclusive_minimum: float | None = None
    maximum: float | None = None
    exclusive_maximum: float | None = None
    multiple_of: float | None = None


@dataclass(frozen=True)
class ArrayConstraints:
    """
    Assertions that apply to an array instance.
    """

    min_items: int | None = None
    max_items: int | None = None
    unique_items: bool = False


@dataclass(frozen=True)
class ObjectConstraints:
    """Assertions that apply to an object instance, other than `required`."""

    min_properties: int | None = None
    max_properties: int | None = None


@dataclass(frozen=True)
class Discriminator:
    """Polymorphism hint. A vendor keyword layered on JSON Schema, not part of it."""

    property_name: str = ""
    mapping: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Schema:
    """One schema node."""

    # -- reference ----------------------------------------------------------
    #: A `$ref`, verbatim as written. Whatever else the node declares still
    #: applies: 2020-12 composes it, earlier drafts discard it, and this model
    #: keeps it either way.
    ref: str | None = None
    #: The component name `ref` ends in. `#/definitions/Pet` and
    #: `#/components/schemas/Pet` both give `Pet`, so two dialects naming the
    #: same target agree on the part that identifies it.
    ref_name: str | None = None

    # -- annotation ---------------------------------------------------------
    title: str | None = None
    description: str | None = None
    default: Any = UNSET
    examples: tuple[Any, ...] = ()
    deprecated: bool = False
    read_only: bool = False
    write_only: bool = False

    # -- type ---------------------------------------------------------------
    #: Declared types with `"null"` removed - that becomes `nullable`. Usually
    #: one entry; 2020-12 also permits a union such as `["string", "integer"]`.
    types: tuple[str, ...] = ()
    #: Whether `null` is permitted. A flag rather than a `types` member:
    #: `"null"` states nullability, which is not a type of the value.
    nullable: bool = False
    format: str | None = None
    enum: tuple[Any, ...] = ()
    const: Any = UNSET

    # -- object -------------------------------------------------------------
    properties: dict[str, Schema] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    additional_properties: bool | Schema | None = None

    # -- array --------------------------------------------------------------
    items: Schema | None = None
    #: Tuple validation: one schema per position.
    prefix_items: tuple[Schema, ...] = ()

    # -- constraints, by the instance type they assert on ---------------------
    string_constraints: StringConstraints | None = None
    numeric_constraints: NumericConstraints | None = None
    array_constraints: ArrayConstraints | None = None
    object_constraints: ObjectConstraints | None = None

    # -- composition --------------------------------------------------------
    all_of: tuple[Schema, ...] = ()
    any_of: tuple[Schema, ...] = ()
    one_of: tuple[Schema, ...] = ()
    #: Trailing underscore: `not` is a keyword.
    not_: Schema | None = None

    # -- vendor additions ---------------------------------------------------
    discriminator: Discriminator | None = None
    external_docs: ExternalDocs | None = None

    extensions: dict[str, Any] = field(default_factory=dict)

    def is_ref(self) -> bool:
        """Whether this node carries a `$ref`. It may carry keywords too."""
        return self.ref is not None

    def is_property_required(self, name: str) -> bool:
        """Whether the named property is listed in `required`."""
        return name in self.required

    def schema_shape(self) -> SchemaShape:
        if self.is_ref():
            return SchemaShape.REF
        if self.properties or self.additional_properties is not None:
            return SchemaShape.OBJECT
        if self.items or self.prefix_items:
            return SchemaShape.ARRAY
        if self.all_of or self.any_of or self.one_of:
            return SchemaShape.COMPOSITION
        if "object" in self.types:
            return SchemaShape.OBJECT
        if "array" in self.types:
            return SchemaShape.ARRAY
        return SchemaShape.PRIMITIVE
