from __future__ import annotations

import unittest

from mkdocs_owl_api.common.base import RenderContext, join_blocks
from mkdocs_owl_api.common.builders import (
    AttachmentsBuilder,
    SchemaBuilder,
    SchemaTableBuilder,
    SchemasBuilder,
    SecurityBuilder,
)
from mkdocs_owl_api.options import PageOptions, ResolvedAttachment


def _ctx(spec=None, *, spec_url="", attachments=(), **opts) -> RenderContext:
    return RenderContext(
        spec=spec if spec is not None else {},
        options=PageOptions(type="openapi", **opts),
        spec_url=spec_url,
        attachments=tuple(attachments),
    )


class TestSchemaTableBuilder(unittest.TestCase):
    SCHEMA = {
        "properties": {
            "id": {"type": "string"},
            "nested": {"properties": {"deep": {"type": "integer"}}},
            "secret": {"type": "string", "x-internal-only": True},
        },
        "required": ["id"],
    }

    def test_no_properties_omits_the_section(self):
        self.assertEqual(SchemaTableBuilder(_ctx(), {}).build(), [])
        self.assertEqual(SchemaTableBuilder(_ctx(), {"type": "string"}).build(), [])

    def test_single_block_with_headers(self):
        blocks = SchemaTableBuilder(_ctx(), self.SCHEMA).build()
        self.assertEqual(len(blocks), 1)
        self.assertIn("<tr><th>Name</th><th>Type</th><th>Description</th></tr>", blocks[0])
        self.assertTrue(blocks[0].startswith("<table>"))
        self.assertTrue(blocks[0].endswith("</table>"))

    def test_block_carries_no_trailing_blank(self):
        # The block protocol requires it; the container owns separators.
        block = SchemaTableBuilder(_ctx(), self.SCHEMA).build()[0]
        self.assertEqual(block, block.strip("\n"))

    def test_nested_properties_get_dotted_paths(self):
        block = SchemaTableBuilder(_ctx(), self.SCHEMA).build()[0]
        self.assertIn("nested.", block)
        self.assertIn("deep", block)

    def test_max_depth_stops_the_walk(self):
        rows = SchemaTableBuilder(_ctx(schema_depth=1), self.SCHEMA).rows()
        self.assertNotIn("nested.deep", [path for path, _, _, _ in rows])

    def test_hide_internal_drops_flagged_properties(self):
        shown = SchemaTableBuilder(_ctx(), self.SCHEMA).build()[0]
        hidden = SchemaTableBuilder(_ctx(hide_internal=True), self.SCHEMA).build()[0]
        self.assertIn("secret", shown)
        self.assertNotIn("secret", hidden)

    def test_all_properties_hidden_omits_the_table(self):
        schema = {"properties": {"secret": {"type": "string", "x-internal-only": True}}}
        self.assertEqual(SchemaTableBuilder(_ctx(hide_internal=True), schema).build(), [])

    def test_array_of_objects_marked_and_walked(self):
        schema = {"properties": {"items": {
            "type": "array", "items": {"properties": {"sku": {"type": "string"}}},
        }}}
        block = SchemaTableBuilder(_ctx(), schema).build()[0]
        self.assertIn("array of objects", block)
        self.assertIn("sku", block)


class TestSchemaBuilder(unittest.TestCase):
    def test_ref_short_circuits_after_description(self):
        blocks = SchemaBuilder(_ctx(), {
            "description": "A user.", "$ref": "#/components/schemas/User",
        }).build()
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0], "A user.")
        self.assertTrue(blocks[1].startswith("_Type:_ "))

    def test_enum_without_properties_lists_values_as_one_block(self):
        blocks = SchemaBuilder(_ctx(), {"type": "string", "enum": ["a", "b"]}).build()
        self.assertEqual(blocks[-1], "- `a`\n- `b`")
        self.assertIn("**Allowed values:**", blocks)

    def test_all_of_merges_properties_into_the_table(self):
        blocks = SchemaBuilder(_ctx(), {
            "allOf": [
                {"$ref": "#/components/schemas/Base"},
                {"properties": {"extra": {"type": "string"}}, "required": ["extra"]},
            ],
        }).build()
        joined = join_blocks(blocks)
        self.assertIn("**All of:**", joined)
        self.assertIn("_Properties:_", joined)
        self.assertIn("extra", joined)

    def test_one_of_and_any_of_render_lines(self):
        joined = join_blocks(SchemaBuilder(_ctx(), {
            "oneOf": [{"type": "string"}], "anyOf": [{"$ref": "#/components/schemas/X"}],
        }).build())
        self.assertIn("**One of:**", joined)
        self.assertIn("**Any of:**", joined)

    def test_properties_label_survives_a_fully_hidden_table(self):
        blocks = SchemaBuilder(_ctx(hide_internal=True), {
            "type": "object",
            "properties": {"secret": {"type": "string", "x-internal-only": True}},
        }).build()
        self.assertEqual(blocks[-1], "_Properties:_")

    def test_empty_schema_renders_nothing(self):
        self.assertEqual(SchemaBuilder(_ctx(), {}).build(), [])


class TestSchemasBuilder(unittest.TestCase):
    SPEC = {"components": {"schemas": {
        "User": {"type": "object", "properties": {"id": {"type": "string"}}},
        "Tag": {"type": "string"},
    }}}

    def test_absent_or_empty_omits_the_section(self):
        self.assertEqual(SchemasBuilder(_ctx()).build(), [])
        self.assertEqual(SchemasBuilder(_ctx({"components": {}})).build(), [])
        self.assertEqual(SchemasBuilder(_ctx({"components": {"schemas": {}}})).build(), [])

    def test_heading_and_anchors(self):
        blocks = SchemasBuilder(_ctx(self.SPEC)).build()
        self.assertEqual(blocks[0], "## Schemas")
        self.assertIn("### User {#schemas-user}", blocks)
        self.assertIn("### Tag {#schemas-tag}", blocks)

    def test_schema_order_is_preserved(self):
        blocks = SchemasBuilder(_ctx(self.SPEC)).build()
        self.assertLess(
            blocks.index("### User {#schemas-user}"),
            blocks.index("### Tag {#schemas-tag}"),
        )

    def test_non_dict_entries_are_skipped(self):
        blocks = SchemasBuilder(_ctx({"components": {"schemas": {"Bad": "nope"}}})).build()
        self.assertEqual(blocks, ["## Schemas"])


class TestAttachmentsBuilder(unittest.TestCase):
    def test_nothing_to_show_omits_the_section(self):
        self.assertEqual(AttachmentsBuilder(_ctx(), "OpenAPI").build(), [])

    def test_spec_row_uses_the_flavour_label_and_format(self):
        block = AttachmentsBuilder(_ctx(spec_url="../a/spec.yml"), "AsyncAPI").build()[0]
        self.assertIn("[Specification Source](../a/spec.yml)", block)
        self.assertIn("AsyncAPI specification in yml format", block)

    def test_hide_download_link_drops_only_the_spec_row(self):
        ctx = _ctx(
            spec_url="s.json",
            attachments=[ResolvedAttachment(title="Guide", description="d", url="g.pdf")],
            hide_download_link=True,
        )
        block = AttachmentsBuilder(ctx, "OpenAPI").build()[0]
        self.assertNotIn("Specification Source", block)
        self.assertIn("[Guide](g.pdf)", block)

    def test_failed_attachment_reports_the_error(self):
        ctx = _ctx(attachments=[ResolvedAttachment(title="Missing", error="not found")])
        block = AttachmentsBuilder(ctx, "OpenAPI").build()[0]
        self.assertIn("_(unavailable: not found)_", block)

    def test_pipe_in_cell_is_escaped(self):
        ctx = _ctx(attachments=[
            ResolvedAttachment(title="a|b", url="x", description="c|d"),
        ])
        block = AttachmentsBuilder(ctx, "OpenAPI").build()[0]
        self.assertIn("a\\|b", block)
        self.assertIn("c\\|d", block)


class TestSecurityBuilder(unittest.TestCase):
    SPEC = {"components": {"securitySchemes": {
        "oauth": {"type": "oauth2", "description": "OAuth."},
        "key": {"type": "apiKey", "name": "X-Key", "in": "header"},
    }}}

    def test_non_dict_entry_renders_nothing(self):
        self.assertEqual(SecurityBuilder(_ctx(self.SPEC), "nope").build(), [])
        self.assertEqual(SecurityBuilder(_ctx(self.SPEC), {}).build(), [])

    def test_unknown_scheme_degrades_to_a_bullet(self):
        blocks = SecurityBuilder(_ctx(self.SPEC), {"nosuch": []}).build()
        self.assertEqual(blocks, ["- **Security:** `nosuch`"])

    def test_admonition_carries_scheme_details(self):
        block = SecurityBuilder(_ctx(self.SPEC), {"key": []}).build()[0]
        self.assertTrue(block.startswith('!!! note ":material-security: Security: key"'))
        self.assertIn("**Name:** `X-Key`", block)
        self.assertIn("**In:** `header`", block)

    def test_scopes_are_listed(self):
        block = SecurityBuilder(_ctx(self.SPEC), {"oauth": ["read", "write"]}).build()[0]
        self.assertIn("**Scopes:** `read`, `write`", block)

    def test_body_lines_are_indented_under_the_admonition(self):
        block = SecurityBuilder(_ctx(self.SPEC), {"key": []}).build()[0]
        for line in block.splitlines()[1:]:
            if line:
                self.assertTrue(line.startswith("    "), line)


if __name__ == "__main__":
    unittest.main()
