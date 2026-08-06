"""
JSON Schema model, normalised onto the 2020-12 vocabulary.

Shaped for rendering rather than validation: nothing here evaluates a schema
against an instance, so keywords that only change an assertion outcome are
absent - `if`/`then`/`else`, `dependentSchemas`, `dependentRequired`,
`patternProperties`, `propertyNames`, `unevaluatedItems`,
`unevaluatedProperties`, `$id`, `$anchor`, `$dynamicRef`, `contentEncoding`,
`contentMediaType`. Add one when something puts it on a page.

References are kept, never inlined - see `SchemaRef`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

from .doc_model import ExternalDocs


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

#: Anywhere a subschema may appear, a `$ref` may appear instead.
#:
#: Spelled with `typing.Union` because this is a runtime expression, not an
#: annotation: `from __future__ import annotations` does not defer it, and the
#: `Schema | SchemaRef` form would fail on the supported 3.9 floor.
SchemaLike = Union["Schema", "SchemaRef"]


@dataclass(frozen=True)
class SchemaRef:
    """
    A `$ref`, kept rather than resolved into its target.

    Inlining would destroy the identity needed to link into the schemas section,
    and a self-referencing schema cannot be inlined at all.
    """

    #: Source spelling, e.g. `#/components/schemas/Pet`.
    pointer: str = ""
    #: Component it resolves to, so equal targets compare equal on the part
    #: that matters regardless of where the components live.
    name: str = ""
    #: Meaningful only where annotations beside a `$ref` are allowed.
    summary: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class Bound:
    """A numeric limit and whether it is exclusive: `>` versus `>=`."""

    value: float
    exclusive: bool = False


@dataclass(frozen=True)
class Discriminator:
    """Polymorphism hint. An OpenAPI keyword, not a JSON Schema one."""

    property_name: str = ""
    mapping: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Schema:
    """One schema node. Any subschema slot may hold a `SchemaRef` instead."""

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
    #: Whether `null` is permitted. A flag rather than a `types` member, so
    #: rendering "string (nullable)" needs no list handling.
    nullable: bool = False
    format: str | None = None
    enum: tuple[Any, ...] = ()
    const: Any = UNSET

    # -- object -------------------------------------------------------------
    properties: dict[str, SchemaLike] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    #: `False` forbids extra keys, `True` allows any, a schema constrains them,
    #: `None` means the keyword was absent.
    additional_properties: bool | SchemaLike | None = None
    min_properties: int | None = None
    max_properties: int | None = None

    # -- array --------------------------------------------------------------
    items: SchemaLike | None = None
    #: Tuple validation: one schema per position.
    prefix_items: tuple[SchemaLike, ...] = ()
    min_items: int | None = None
    max_items: int | None = None
    unique_items: bool = False

    # -- string -------------------------------------------------------------
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None

    # -- numeric ------------------------------------------------------------
    minimum: Bound | None = None
    maximum: Bound | None = None
    multiple_of: float | None = None

    # -- composition --------------------------------------------------------
    all_of: tuple[SchemaLike, ...] = ()
    any_of: tuple[SchemaLike, ...] = ()
    one_of: tuple[SchemaLike, ...] = ()
    #: Trailing underscore: `not` is a keyword.
    not_: SchemaLike | None = None

    # -- openapi additions --------------------------------------------------
    discriminator: Discriminator | None = None
    external_docs: ExternalDocs | None = None

    extensions: dict[str, Any] = field(default_factory=dict)
