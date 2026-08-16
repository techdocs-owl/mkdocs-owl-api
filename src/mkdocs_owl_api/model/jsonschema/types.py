"""
Model ot A JSON Schema document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..doc_types import ApiDoc
from .schema_types import Schema


class JsonSchemaDialect(Enum):
    """
    Source dialects.
    """

    DRAFT_04 = "draft-04"
    DRAFT_06 = "draft-06"
    DRAFT_07 = "draft-07"
    DRAFT_2019_09 = "2019-09"
    DRAFT_2020_12 = "2020-12"


@dataclass(frozen=True)
class JsonSchemaDoc(ApiDoc):
    """
    A JsonSchema document.

    `root` is the document itself read as a schema;
    `definitions` are the reusable subschemas, from `$defs` or `definitions` depending on the dialect.
    """

    dialect: JsonSchemaDialect = JsonSchemaDialect.DRAFT_2020_12
    schema_id: str | None = None
    root: Schema = field(default_factory=Schema)
    definitions: dict[str, Schema] = field(default_factory=dict)

    @property
    def spec_version_key(self) -> str:
        return "json-schema"
