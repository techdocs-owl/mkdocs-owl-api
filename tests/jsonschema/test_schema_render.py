"""
Tests for the JSON Schema type system's renderer.
"""

from __future__ import annotations

import re
import unittest

from mkdocs_owl_api.model.parse_report import Reporter
from mkdocs_owl_api.model.jsonschema.schema_types import SchemaShape
from mkdocs_owl_api.model.jsonschema.schema_parser import read_schema
from mkdocs_owl_api.jsonschema.schema_render import render_schema


def render(raw, **options):
    options.setdefault("max_depth", 3)
    schema = read_schema(raw, Reporter())
    return "\n".join(render_schema(schema, **options))


ALTERNATIVES = '<ul class="techdocs-owl-api-alternatives">'


class TestAllOf(unittest.TestCase):

    def test_referenced_members_are_named_on_one_line(self):
        out = render({"type": "object",
                      "allOf": [{"$ref": "#/$defs/A"}, {"$ref": "#/$defs/B"}]})
        self.assertIn("**All of:** [`A`](#schemas-a) | [`B`](#schemas-b)", out)
        self.assertNotIn(ALTERNATIVES, out)

    def test_an_inline_member_is_listed_with_its_own_table(self):
        out = render({
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "allOf": [{"properties": {"b": {"type": "integer"}}, "required": ["b"]}],
        })
        self.assertIn("<strong>All of:</strong>", out)
        self.assertIn(ALTERNATIVES, out)
        self.assertIn(">a</span>", out)
        self.assertIn(">b</span>", out)
        self.assertEqual(out.count("<table>"), 2)


class TestAlternatives(unittest.TestCase):

    def test_each_member_becomes_an_item(self):
        out = render({"oneOf": [{"type": "string"}, {"type": "integer"}]})
        self.assertIn("<strong>One of:</strong>", out)
        self.assertIn(ALTERNATIVES, out)
        self.assertEqual(out.count("<li>"), 2)

    def test_any_of_is_labelled_separately(self):
        out = render({"anyOf": [{"type": "string"}, {"type": "integer"}]})
        self.assertIn("<strong>Any of:</strong>", out)

    def test_both_keywords_on_one_schema_get_a_list_each(self):
        out = render({"oneOf": [{"type": "string"}],
                      "anyOf": [{"type": "integer"}]})
        self.assertIn("<strong>One of:</strong>", out)
        self.assertIn("<strong>Any of:</strong>", out)
        self.assertEqual(out.count(ALTERNATIVES), 2)

    def test_a_member_description_is_kept(self):
        out = render({"oneOf": [
            {"type": "string", "description": "The short form."},
            {"type": "array", "description": "The long form."},
        ]})
        self.assertIn("The short form.", out)
        self.assertIn("The long form.", out)

    def test_a_member_carries_its_constraints(self):
        out = render({"oneOf": [{"type": "string", "enum": ["all"]},
                                {"type": "integer"}]})
        self.assertIn("Allowed values", out)
        self.assertIn("<code>all</code>", out)

    def test_an_object_member_carries_its_property_table(self):
        out = render({"oneOf": [
            {"type": "string"},
            {"type": "object", "properties": {"path": {"type": "string"}}},
        ]})
        self.assertIn("<table>", out)
        self.assertIn(">path</span>", out)
        # The table sits inside its own alternative, not after the list.
        self.assertLess(out.index("<table>"), out.rindex("</ul>"))

    def test_a_referenced_member_links_and_is_not_expanded(self):
        out = render({"oneOf": [{"$ref": "#/$defs/Thing"}]})
        self.assertIn("#schemas-thing", out)
        self.assertNotIn("<table>", out)


class TestNesting(unittest.TestCase):
    @staticmethod
    def nested(depth):
        node = {"type": "string", "description": "leaf"}
        for level in range(depth, 0, -1):
            node = {"oneOf": [{"type": "integer",
                               "description": f"scalar at {level}"}, node]}
        return node

    def test_alternatives_nest(self):
        out = render(self.nested(2))
        self.assertEqual(out.count(ALTERNATIVES), 2)
        self.assertIn("scalar at 2", out)

    def test_nesting_stops_at_three_levels(self):
        for depth in (4, 5, 8):
            with self.subTest(depth=depth):
                out = render(self.nested(depth))
                self.assertEqual(out.count(ALTERNATIVES), 3)

    def test_the_cap_names_what_it_stops_listing(self):
        out = render(self.nested(4))
        self.assertIn("<strong>One of:</strong> ", out)

    def test_a_self_referential_schema_terminates(self):
        out = render({"oneOf": [{"$ref": "#/$defs/Node"}, {"type": "null"}]})
        self.assertIn("#schemas-node", out)


class TestMarkupShape(unittest.TestCase):
    def test_items_are_closed(self):
        out = render({"oneOf": [{"type": "string"}, {"type": "integer"}]})
        self.assertEqual(out.count("<li>"), out.count("</li>"))
        self.assertEqual(out.count("<ul"), out.count("</ul>"))


class TestShapeDispatch(unittest.TestCase):

    def shape(self, raw):
        return read_schema(raw, Reporter()).schema_shape()

    def test_the_order_is_ref_object_array_composition_primitive(self):
        cases = [
            ({"$ref": "#/$defs/A", "type": "object"}, SchemaShape.REF),
            ({"properties": {"a": {}}}, SchemaShape.OBJECT),
            ({"type": "object"}, SchemaShape.OBJECT),
            ({"items": {"type": "string"}}, SchemaShape.ARRAY),
            ({"type": "array"}, SchemaShape.ARRAY),
            ({"type": "object", "oneOf": [{"type": "string"}]}, SchemaShape.OBJECT),
            ({"type": "array", "oneOf": [{"type": "string"}]}, SchemaShape.ARRAY),
            ({"oneOf": [{"type": "string"}]}, SchemaShape.COMPOSITION),
            ({"allOf": [{"$ref": "#/$defs/A"}]}, SchemaShape.COMPOSITION),
            ({"type": "string"}, SchemaShape.PRIMITIVE),
            ({}, SchemaShape.PRIMITIVE),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(self.shape(raw), expected)

    def test_an_object_keyword_does_not_outrank_a_declared_type(self):
        raw = {"type": "array", "additionalProperties": False,
               "items": {"type": "object", "properties": {"driver": {"type": "string"}}}}
        self.assertEqual(self.shape(raw), SchemaShape.ARRAY)
        out = render(raw)
        self.assertIn("_Items:_", out)
        self.assertIn(">driver</span>", out)
        self.assertNotIn("Additional properties are NOT allowed", out)

    def test_enum_is_a_constraint_not_a_shape(self):
        self.assertEqual(self.shape({"type": "string", "enum": ["a"]}),
                         SchemaShape.PRIMITIVE)
        self.assertEqual(self.shape({"type": "object", "properties": {},
                                     "enum": [{"a": 1}]}), SchemaShape.OBJECT)

    def test_a_primitive_keeps_its_allowed_values(self):
        out = render({"type": "string", "enum": ["a", "b"]})
        self.assertIn("Allowed values", out)
        self.assertIn("`a`", out)

    def test_an_object_keeps_its_allowed_values(self):
        out = render({"type": "object", "properties": {"a": {"type": "integer"}},
                      "enum": [{"a": 1}]})
        self.assertIn("Allowed values", out)
        self.assertIn(">a</span>", out)

    def test_a_ref_keeps_its_siblings(self):
        out = render({"$ref": "#/$defs/A", "enum": ["x", "y"], "maxLength": 8})
        self.assertIn("#schemas-a", out)
        self.assertIn("Allowed values", out)
        self.assertIn("Max length", out)

    def test_a_multi_typed_schema_names_every_type(self):
        out = render({"type": ["boolean", "string", "object"],
                      "properties": {"name": {"type": "string"}}})
        self.assertIn("`boolean | string | object`", out)
        self.assertIn(">name</span>", out)


class TestArraySection(unittest.TestCase):
    def test_an_array_names_what_it_holds(self):
        out = render({"type": "array", "items": {"type": "string"}})
        self.assertIn("`array of string`", out)

    def test_an_array_of_objects_expands_its_items(self):
        out = render({"type": "array",
                      "items": {"type": "object",
                                "properties": {"id": {"type": "string"}}}})
        self.assertIn("_Items:_", out)
        self.assertIn(">id</span>", out)

    def test_array_constraints_are_kept(self):
        out = render({"type": "array", "items": {"type": "string"},
                      "minItems": 1, "uniqueItems": True})
        self.assertIn("Min items", out)
        self.assertIn("Unique items", out)


class TestRequiredRestriction(unittest.TestCase):
    def test_any_of_reads_as_a_requirement(self):
        out = render({
            "type": "object",
            "properties": {"text": {"type": "string"}, "id": {"type": "string"}},
            "anyOf": [{"required": ["text"]}, {"required": ["id"]}],
        })
        self.assertIn("**Requires at least one of:** `text` | `id`", out)
        self.assertNotIn(ALTERNATIVES, out)

    def test_one_of_says_exactly_one(self):
        out = render({
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
            "oneOf": [{"required": ["a"]}, {"required": ["b"]}],
        })
        self.assertIn("**Requires exactly one of:** `a` | `b`", out)

    def test_a_member_with_real_content_is_still_listed(self):
        out = render({
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "oneOf": [{"required": ["a"]}, {"type": "object",
                                            "properties": {"b": {"type": "string"}}}],
        })
        self.assertIn(ALTERNATIVES, out)
        self.assertNotIn("Requires", out)


class TestObjectVersusComposition(unittest.TestCase):
    def test_no_declared_type_makes_the_composition_the_content(self):
        raw = {"allOf": [{"$ref": "#/$defs/A"}, {"$ref": "#/$defs/B"}]}
        self.assertEqual(read_schema(raw, Reporter()).schema_shape(),
                         SchemaShape.COMPOSITION)
        out = render(raw)
        self.assertIn("**All of:** [`A`](#schemas-a) | [`B`](#schemas-b)", out)
        self.assertNotIn(ALTERNATIVES, out)

    def test_a_declared_type_makes_the_composition_a_constraint(self):
        raw = {"type": "object",
               "allOf": [{"$ref": "#/$defs/A"}, {"$ref": "#/$defs/B"}]}
        self.assertEqual(read_schema(raw, Reporter()).schema_shape(),
                         SchemaShape.OBJECT)
        out = render(raw)
        self.assertIn("**All of:** [`A`](#schemas-a) | [`B`](#schemas-b)", out)
        self.assertNotIn(ALTERNATIVES, out)

    def test_own_properties_make_the_composition_a_constraint(self):
        raw = {"properties": {"types": {"type": "string"}},
               "allOf": [{"$ref": "#/$defs/eventObject"}]}
        self.assertEqual(read_schema(raw, Reporter()).schema_shape(),
                         SchemaShape.OBJECT)
        out = render(raw)
        self.assertIn("#schemas-eventobject", out)
        self.assertIn(">types</span>", out)

    def test_members_that_render_to_nothing_are_dropped(self):
        raw = {"type": "object",
               "properties": {"default": {"type": "string"}},
               "allOf": [{"if": {"required": ["type"]},
                          "then": {"properties": {"default": {"type": "string"}}}}
                         for _ in range(5)]}
        out = render(raw)
        self.assertNotIn("All of", out)
        self.assertNotIn(ALTERNATIVES, out)
        self.assertIn(">default</span>", out)

    def test_bare_references_collapse_to_one_line(self):
        out = render({"oneOf": [{"$ref": "#/$defs/A"}, {"$ref": "#/$defs/B"}]})
        self.assertIn("**One of:** [`A`](#schemas-a) | [`B`](#schemas-b)", out)
        self.assertNotIn(ALTERNATIVES, out)

    def test_a_described_reference_is_listed_instead(self):
        out = render({"oneOf": [{"$ref": "#/$defs/A", "description": "The short form."},
                                {"$ref": "#/$defs/B"}]})
        self.assertIn(ALTERNATIVES, out)
        self.assertIn("The short form.", out)


if __name__ == "__main__":
    unittest.main()
