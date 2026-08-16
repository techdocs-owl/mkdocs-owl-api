"""
JSON Schema page renderer.
"""

from __future__ import annotations

from dataclasses import replace

from ..common.primitives.markup import _anchor, _heading
from ..common.render import MarkdownRenderer
from ..model.jsonschema.types import JsonSchemaDoc
from .schema_render import render_schema


class JsonSchemaRenderer(MarkdownRenderer):
    doc: JsonSchemaDoc

    def sections(self) -> list[str]:
        return self.identifier() + self.root_schema() + self.definitions()

    def specification_line(self) -> list[str]:
        return [
            ":material-file-code: **Specification:** "
            f"`{self.doc.spec_version_key} {self.doc.dialect.value}`"
        ]

    def identifier(self) -> list[str]:
        if not self.doc.schema_id:
            return []
        return [f"**Schema ID:** `{self.doc.schema_id}`"]

    def root_schema(self) -> list[str]:
        blocks = render_schema(
            replace(self.doc.root, description=None),
            hide_internal=self.options.hide_internal,
            max_depth=self.options.schema_depth,
        )
        return ["## Schema", *blocks] if blocks else []

    def definitions(self) -> list[str]:
        """
        List of re-usable schemas.
        The anchors are `schemas-<definition-name>`.
        """
        if not self.doc.definitions:
            return []
        blocks: list[str] = ["## Definitions"]
        for name, schema in self.doc.definitions.items():
            blocks.append(_heading(3, name, anchor=_anchor("schemas", name)))
            blocks.extend(render_schema(
                schema,
                hide_internal=self.options.hide_internal,
                max_depth=self.options.schema_depth,
            ))
        return blocks


