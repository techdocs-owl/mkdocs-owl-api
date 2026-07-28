from __future__ import annotations

import unittest

from mkdocs_owl_api.render import common


class TestHelpers(unittest.TestCase):
    def test_unescape_pointer(self):
        self.assertEqual(common._unescape_pointer("~1users"), "/users")
        self.assertEqual(common._unescape_pointer("a~0b"), "a~b")
        self.assertEqual(common._unescape_pointer("~01"), "~1")

    def test_resolve_ref(self):
        spec = {"paths": {"/users": {"x": 1}},
                "components": {"schemas": {"We~rd": {"type": "object"}}}}
        self.assertEqual(common._resolve_ref(spec, "#/paths/~1users"), {"x": 1})
        self.assertEqual(common._resolve_ref(spec, "#/components/schemas/We~0rd"),
                         {"type": "object"})
        self.assertIsNone(common._resolve_ref(spec, "#/nope/missing"))

    def test_ref_link(self):
        self.assertEqual(common._ref_link("#/components/schemas/Foo"),
                         "[`Foo`](#schemas-foo)")
        self.assertIn("users-get", common._ref_link("#/paths/~1users/get"))

    def test_schema_depth(self):
        self.assertEqual(common._schema_depth({}), 3)
        self.assertEqual(common._schema_depth({"schema_depth": 5}), 5)
        self.assertEqual(common._schema_depth({"schema_depth": 0}), 1)
        self.assertEqual(common._schema_depth({"schema_depth": "x"}), 3)

    def test_format_type(self):
        self.assertEqual(common._format_type({"type": "string", "format": "uuid"}),
                         "string (uuid)")
        self.assertEqual(common._format_type({"type": "array", "items": {"type": "string"}}),
                         "array of string")
        self.assertEqual(common._format_type({"$ref": "#/components/schemas/Foo"}),
                         "[`Foo`](#schemas-foo)")

    def test_format_type_additional_properties(self):
        self.assertEqual(
            common._format_type(
                {"type": "object", "additionalProperties": {"type": "integer"}}),
            "map of string → integer")
        # A bool toggle is not a value schema - `false` is just a closed object.
        self.assertEqual(
            common._format_type({"type": "object", "additionalProperties": False}),
            "object")
        self.assertEqual(
            common._format_type({"type": "object", "additionalProperties": True}),
            "map of string → any")

    def test_format_type_single_all_of(self):
        # `allOf` with one member means "conforms to it", not "array of it".
        self.assertEqual(
            common._format_type(
                {"allOf": [{"$ref": "#/components/schemas/Foo"}],
                 "description": "a foo"}),
            "[`Foo`](#schemas-foo)")
        self.assertEqual(
            common._format_type({"allOf": [{"type": "string", "format": "uuid"}]}),
            "string (uuid)")
        # An explicit sibling type wins over the composed member.
        self.assertEqual(
            common._format_type(
                {"type": "string", "allOf": [{"$ref": "#/components/schemas/Foo"}]}),
            "string")

    def test_format_type_enum_without_type(self):
        # An enum with no sibling `type` takes the type of its values.
        self.assertEqual(common._format_type({"enum": ["OPEN", "CLOSED"]}), "string")
        self.assertEqual(common._format_type({"enum": [1, 2]}), "integer")
        self.assertEqual(common._format_type({"enum": [1.5]}), "number")
        self.assertEqual(common._format_type({"enum": [True, False]}), "boolean")
        # An explicit type still wins.
        self.assertEqual(
            common._format_type({"type": "string", "enum": [1, 2]}), "string")
        # Mixed values are reported as such, not collapsed.
        self.assertEqual(common._format_type({"enum": ["a", 1]}), "integer | string")
        self.assertEqual(common._format_type({"enum": ["a", None]}), "null | string")
        # No enum, no type - unchanged fallback.
        self.assertEqual(common._format_type({}), "object")
        self.assertEqual(common._format_type({"enum": []}), "object")

    def test_format_type_non_dict(self):
        self.assertEqual(common._format_type(True), "any")
        self.assertEqual(common._format_type(None), "any")
        self.assertEqual(
            common._format_type({"type": "array", "items": [{"type": "string"}]}),
            "array of any")

    def test_property_name_html(self):
        self.assertEqual(common._property_name_html("id"),
                         '<span class="techdocs-owl-api-prop">id</span>')
        self.assertEqual(
            common._property_name_html("rows[].label"),
            '<span class="techdocs-owl-api-path">rows[].<wbr></span>'
            '<span class="techdocs-owl-api-prop">label</span>')
        # Only the last segment is the leaf, however deep the path, and every
        # dot carries a break opportunity.
        self.assertEqual(
            common._property_name_html("a.b.c"),
            '<span class="techdocs-owl-api-path">a.<wbr>b.<wbr></span>'
            '<span class="techdocs-owl-api-prop">c</span>')
        # Names are plain text now - no code formatting.
        self.assertNotIn("<code>", common._property_name_html("a.b"))
        self.assertIn("&lt;x&gt;", common._property_name_html("<x>"))

    def test_render_tags(self):
        out = common._render_tags([{"name": "orders", "description": "Order stuff"}])
        self.assertIn("techdocs-owl-api-pill--tag", out)
        self.assertIn('title="Order stuff"', out)
        self.assertEqual(common._render_tags([]), "")
        self.assertEqual(common._render_tags(None), "")


class TestSchemaRendering(unittest.TestCase):
    NESTED = {
        "type": "object",
        "required": ["order"],
        "properties": {
            "order": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": "string"},
                                "meta": {"type": "object",
                                         "properties": {"k": {"type": "string"}}},
                            },
                        },
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    }

    def _names(self, depth):
        rows = common._flatten_properties(
            self.NESTED["properties"], set(self.NESTED.get("required") or []),
            hide_internal=False, max_depth=depth,
        )
        return [(n, t) for (n, _p, _r, t) in rows]

    def test_properties_flatten(self):
        names = dict(self._names(3))
        self.assertIn("order", names)
        self.assertIn("order.id", names)
        self.assertEqual(names.get("order.items[]"), "array of objects")
        self.assertIn("order.items[].sku", names)
        self.assertIn("order.tags", names)
        self.assertNotIn("order.tags[]", names)

    def test_properties_depth_cap(self):
        d3 = dict(self._names(3))
        self.assertIn("order.items[].meta", d3)
        self.assertNotIn("order.items[].meta.k", d3)
        d5 = dict(self._names(5))
        self.assertIn("order.items[].meta.k", d5)

    def test_properties_depth_one(self):
        self.assertEqual([n for n, _ in self._names(1)], ["order"])

    def test_properties_hide_internal(self):
        sch = {"type": "object", "properties": {
            "pub": {"type": "string"},
            "secret": {"type": "string", "x-internal-only": True},
            "grp": {"type": "object", "properties": {
                "hidden": {"type": "string", "x-internal-only": True},
                "shown": {"type": "string"},
            }},
        }}
        rows = common._flatten_properties(sch["properties"], set(),
                                          hide_internal=True, max_depth=5)
        names = [n for (n, _p, _r, _t) in rows]
        self.assertIn("pub", names)
        self.assertNotIn("secret", names)
        self.assertIn("grp.shown", names)
        self.assertNotIn("grp.hidden", names)

    def test_schema_composition(self):
        sch = {
            "type": "object",
            "oneOf": [{"$ref": "#/components/schemas/A"},
                      {"$ref": "#/components/schemas/B"}],
            "properties": {"id": {"type": "string"}},
        }
        out = common._render_schema(sch, hide_internal=False)
        self.assertIn("**One of:**", out)
        self.assertIn("[`A`](#schemas-a)", out)
        self.assertIn("[`B`](#schemas-b)", out)

    def test_schema_allof(self):
        sch = {"type": "object",
               "allOf": [{"properties": {"a": {"type": "string"}}},
                         {"$ref": "#/components/schemas/Base"}]}
        out = common._render_schema(sch, hide_internal=False)
        self.assertIn("**All of:**", out)
        self.assertIn("[`Base`](#schemas-base)", out)
        self.assertIn('<span class="techdocs-owl-api-prop">a</span>', out)

    def test_nested_property_path_dims_ancestors(self):
        sch = {"type": "object",
               "properties": {
                   "wrapper": {"type": "object",
                               "properties": {"nodeId": {"type": "string"}}}}}
        out = common._render_schema(sch, hide_internal=False)
        self.assertIn(
            '<span class="techdocs-owl-api-path">wrapper.<wbr></span>'
            '<span class="techdocs-owl-api-prop">nodeId</span>',
            out)
        self.assertIn('<span class="techdocs-owl-api-prop">wrapper</span>', out)

    def test_closed_object_note(self):
        sch = {"type": "object", "additionalProperties": False,
               "properties": {"kind": {"type": "object",
                                       "additionalProperties": False,
                                       "description": "A thing."}}}
        out = common._render_schema(sch, hide_internal=False)
        self.assertEqual(out.count("Additional properties are NOT allowed."), 2)
        self.assertIn('<span class="techdocs-owl-api-note">', out)
        # The note follows the description rather than replacing it.
        self.assertIn("A thing.", out)

    def test_closed_object_note_absent(self):
        for extra in ({}, {"additionalProperties": True},
                      {"additionalProperties": {"type": "string"}}):
            sch = {"type": "object", "properties": {"a": {"type": "string"}}, **extra}
            out = common._render_schema(sch, hide_internal=False)
            self.assertNotIn("Additional properties are NOT allowed.", out)

    def test_schema_labels(self):
        out = common._render_schema({"type": "object",
                                     "properties": {"id": {"type": "string"}}},
                                    hide_internal=False)
        self.assertIn("_Type:_", out)
        self.assertIn("_Properties:_", out)
        self.assertNotIn("**Type:**", out)
        self.assertNotIn("**Properties**", out)

    def test_schema_enum(self):
        out = common._render_schema({"type": "string", "enum": ["x", "y"]},
                                    hide_internal=False)
        self.assertIn("**Allowed values:**", out)
        self.assertIn("`x`", out)


class TestErrorPage(unittest.TestCase):
    def test_error_page(self):
        out = common._error_page("spec parse error", "boom")
        self.assertIn('!!! danger "spec parse error"', out)
        self.assertIn("boom", out)


class TestDownloadsTable(unittest.TestCase):
    def test_downloads_attachments(self):
        out = common._render_downloads_table(
            "../assets/techdocs-owl-api/x.json",
            [{"title": "Proto", "url": "../assets/techdocs-owl-api/x-a.proto", "error": None},
             {"title": "Bad", "url": None, "error": "404 Not Found"}],
            hide_download=False,
        )
        self.assertIn("Specification Source", out)
        self.assertIn("[Proto]", out)
        self.assertIn("unavailable: 404 Not Found", out)

    def test_downloads_hidden(self):
        out = common._render_downloads_table("x.json", [], hide_download=True)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
