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
        self.assertIn("<code>a</code>", out)

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
