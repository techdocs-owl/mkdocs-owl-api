from __future__ import annotations

import unittest
from dataclasses import replace

from mkdocs_owl_api.common.parse_report import Reporter
from mkdocs_owl_api.common.schema_model import (
    UNSET,
    ArrayConstraints,
    Discriminator,
    NumericConstraints,
    ObjectConstraints,
    Schema,
    StringConstraints,
)
from mkdocs_owl_api.common.schema_parser import read_schema

from .fixtures import PET_V2, PET_V30, PET_V31, expected_pet


class SchemaTestCase(unittest.TestCase):
    """
    Base for schema-reading tests.

    `read` asserts a clean parse, so a test that checks translation cannot
    quietly pass while the reader is warning about its input.
    """

    def parse(self, raw):
        report = Reporter()
        return read_schema(raw, report), report.warnings

    def read(self, raw):
        schema, warnings = self.parse(raw)
        self.assertEqual(warnings, (),
                         f"expected a clean parse: {[str(w) for w in warnings]}")
        return schema


class TestTypes(SchemaTestCase):
    def test_scalar_type(self):
        self.assertEqual(self.read({"type": "string"}).types, ("string",))

    def test_type_union_is_kept(self):
        # 2020-12 permits a genuine union, which is why `types` is not scalar.
        self.assertEqual(self.read({"type": ["string", "integer"]}).types,
                         ("string", "integer"))

    def test_format(self):
        self.assertEqual(self.read({"type": "integer", "format": "int64"}).format, "int64")

    def test_file_type_becomes_binary_string(self):
        schema = self.read({"type": "file"})
        self.assertEqual((schema.types, schema.format), (("string",), "binary"))

    def test_bad_type_warns(self):
        schema, warnings = self.parse({"type": 7})
        self.assertEqual(schema.types, ())
        self.assertEqual(len(warnings), 1)
        self.assertIn("expected a string or array", warnings[0].message)

    def test_non_string_type_member_warns(self):
        schema, warnings = self.parse({"type": ["string", 7]})
        self.assertEqual(schema.types, ("string",))
        self.assertEqual(warnings[0].pointer, "#/type/1")


class TestNullable(SchemaTestCase):
    def test_three_spellings_agree(self):
        for raw in ({"type": ["string", "null"]},
                    {"type": "string", "nullable": True},
                    {"type": "string", "x-nullable": True}):
            with self.subTest(raw=raw):
                schema = self.read(raw)
                self.assertTrue(schema.nullable)
                self.assertEqual(schema.types, ("string",))

    def test_absent_is_not_nullable(self):
        self.assertFalse(self.read({"type": "string"}).nullable)

    def test_spellings_or_together(self):
        # `nullable: false` does not un-say a `null` in the type array.
        self.assertTrue(self.read({"type": ["string", "null"], "nullable": False}).nullable)

    def test_consumed_extension_is_not_repeated(self):
        schema = self.read({"type": "string", "x-nullable": True, "x-widget": "chip"})
        self.assertTrue(schema.nullable)
        self.assertEqual(schema.extensions, {"x-widget": "chip"})


class TestNumericConstraints(SchemaTestCase):
    def numeric(self, raw):
        return self.read(raw).numeric_constraints

    def test_draft4_exclusive(self):
        self.assertEqual(self.numeric({"minimum": 5, "exclusiveMinimum": True}),
                         NumericConstraints(exclusive_minimum=5))

    def test_draft4_inclusive(self):
        self.assertEqual(self.numeric({"minimum": 5, "exclusiveMinimum": False}),
                         NumericConstraints(minimum=5))

    def test_2020_12_exclusive(self):
        self.assertEqual(self.numeric({"exclusiveMinimum": 5}),
                         NumericConstraints(exclusive_minimum=5))

    def test_both_limits_are_independent(self):
        # 2020-12 makes these separate keywords, and both assertions apply.
        self.assertEqual(self.numeric({"minimum": 1, "exclusiveMinimum": 5}),
                         NumericConstraints(minimum=1, exclusive_minimum=5))

    def test_plain_limit(self):
        self.assertEqual(self.numeric({"maximum": 9}), NumericConstraints(maximum=9))

    def test_multiple_of(self):
        self.assertEqual(self.numeric({"multipleOf": 2}),
                         NumericConstraints(multiple_of=2))

    def test_zero_limit_is_not_dropped(self):
        # `0` is falsy; the reader must test for absence, not truthiness.
        self.assertEqual(self.numeric({"exclusiveMinimum": 0}),
                         NumericConstraints(exclusive_minimum=0))

    def test_boolean_form_without_limit_warns(self):
        schema, warnings = self.parse({"exclusiveMinimum": True})
        self.assertIsNone(schema.numeric_constraints)
        self.assertIn("needs `minimum`", warnings[0].message)

    def test_bad_exclusive_warns(self):
        schema, warnings = self.parse({"exclusiveMaximum": "5"})
        self.assertIsNone(schema.numeric_constraints)
        self.assertIn("expected a number or boolean", warnings[0].message)


class TestStringConstraints(SchemaTestCase):
    def test_all(self):
        self.assertEqual(
            self.read({"type": "string", "minLength": 1, "maxLength": 3,
                       "pattern": "^a"}).string_constraints,
            StringConstraints(min_length=1, max_length=3, pattern="^a"),
        )


class TestConstraintGroups(SchemaTestCase):
    """
    A constraint is read only where it can assert on something.

    A keyword from another group says nothing about an instance of the declared
    type, so passing it over discards no meaning - and does so in silence.
    """

    ALL = {"minLength": 1, "minimum": 2, "minItems": 3, "minProperties": 4}

    def test_an_untyped_schema_admits_every_group(self):
        schema = self.read(self.ALL)
        self.assertEqual(schema.string_constraints, StringConstraints(min_length=1))
        self.assertEqual(schema.numeric_constraints, NumericConstraints(minimum=2))
        self.assertEqual(schema.array_constraints, ArrayConstraints(min_items=3))
        self.assertEqual(schema.object_constraints, ObjectConstraints(min_properties=4))

    def test_a_declared_type_admits_only_its_own(self):
        schema = self.read({"type": "string", **self.ALL})
        self.assertEqual(schema.string_constraints, StringConstraints(min_length=1))
        self.assertIsNone(schema.numeric_constraints)
        self.assertIsNone(schema.array_constraints)
        self.assertIsNone(schema.object_constraints)

    def test_mismatched_constraints_are_dropped_in_silence(self):
        _, warnings = self.parse({"type": "string", **self.ALL})
        self.assertEqual(warnings, ())

    def test_integer_counts_as_numeric(self):
        self.assertEqual(self.read({"type": "integer", "minimum": 2}).numeric_constraints,
                         NumericConstraints(minimum=2))

    def test_a_type_union_admits_both(self):
        schema = self.read({"type": ["string", "integer"], **self.ALL})
        self.assertEqual(schema.string_constraints, StringConstraints(min_length=1))
        self.assertEqual(schema.numeric_constraints, NumericConstraints(minimum=2))
        self.assertIsNone(schema.array_constraints)

    def test_a_type_with_no_constraints_admits_none(self):
        schema = self.read({"type": "boolean", **self.ALL})
        self.assertIsNone(schema.string_constraints)
        self.assertIsNone(schema.numeric_constraints)

    def test_an_empty_group_is_none(self):
        self.assertIsNone(self.read({"type": "string"}).string_constraints)


class TestRefs(SchemaTestCase):
    def test_bare_ref(self):
        self.assertEqual(
            self.read({"$ref": "#/components/schemas/Pet"}),
            Schema(ref="#/components/schemas/Pet", ref_name="Pet"),
        )

    def test_is_ref(self):
        self.assertTrue(self.read({"$ref": "#/components/schemas/Pet"}).is_ref())
        self.assertFalse(self.read({"type": "string"}).is_ref())

    def test_ref_name_is_dialect_independent(self):
        self.assertEqual(self.read({"$ref": "#/definitions/Pet"}).ref_name,
                         self.read({"$ref": "#/components/schemas/Pet"}).ref_name)

    def test_siblings_apply(self):
        # 2020-12 composes them; 2.0 and 3.0 ignore them, and we do not.
        schema = self.read({"$ref": "#/definitions/User", "readOnly": True,
                            "description": "the owner"})
        self.assertEqual(
            schema,
            Schema(ref="#/definitions/User", ref_name="User",
                   read_only=True, description="the owner"),
        )

    def test_unrepresentable_sibling_is_dropped(self):
        self.assertEqual(
            self.read({"$ref": "#/definitions/Tag", "xml": {"name": "tag"}}),
            Schema(ref="#/definitions/Tag", ref_name="Tag"),
        )

    def test_ref_alongside_composition(self):
        schema = self.read({"$ref": "#/definitions/A", "allOf": [{"type": "string"}]})
        self.assertEqual(schema.ref_name, "A")
        self.assertEqual([s.types for s in schema.all_of], [("string",)])

    def test_self_reference_needs_no_inlining(self):
        schema = self.read({"type": "object",
                            "properties": {"parent": {"$ref": "#/components/schemas/Node"}}})
        self.assertEqual(schema.properties["parent"].ref_name, "Node")

    def test_bad_ref_warns(self):
        schema, warnings = self.parse({"$ref": 7})
        self.assertIsNone(schema.ref)
        self.assertIn("expected a string", warnings[0].message)


class TestRefSiblings(SchemaTestCase):
    """
    A keyword must read the same whether or not a `$ref` sits beside it.

    Checked as a property rather than a list, because a hand-kept list of
    "keywords that count" drifts out of step with the reader - which is how
    `pattern` came to be dropped once.
    """

    REF = "#/components/schemas/Pet"

    SAMPLES = {
        "title": "T", "description": "D", "default": 1, "example": 1,
        "examples": [1], "deprecated": True, "readOnly": True, "writeOnly": True,
        "externalDocs": {"url": "https://x"}, "nullable": True,
        "x-nullable": True, "type": "string", "format": "int64", "enum": ["a"],
        "const": "a", "properties": {"a": {"type": "string"}}, "required": ["a"],
        "additionalProperties": False, "minProperties": 1, "maxProperties": 2,
        "items": {"type": "string"}, "prefixItems": [{"type": "string"}],
        "minItems": 1, "maxItems": 2, "uniqueItems": True, "minLength": 1,
        "maxLength": 2, "pattern": "^a", "minimum": 1, "maximum": 2,
        "exclusiveMinimum": 1, "exclusiveMaximum": 2, "multipleOf": 2,
        "allOf": [{"type": "string"}], "anyOf": [{"type": "string"}],
        "oneOf": [{"type": "string"}], "not": {"type": "string"},
        "discriminator": "kind", "x-widget": "chip",
        # Unrepresentable: these add nothing, with or without a `$ref`.
        "xml": {"name": "pet"}, "if": {"type": "string"},
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "summary": "S",
    }

    def test_a_sibling_reads_the_same_beside_a_ref(self):
        for keyword, value in self.SAMPLES.items():
            with self.subTest(keyword=keyword):
                alone = self.read({keyword: value})
                beside = self.read({"$ref": self.REF, keyword: value})
                self.assertEqual(
                    beside, replace(alone, ref=self.REF, ref_name="Pet"),
                )


class TestArrays(SchemaTestCase):
    def test_single_item_schema(self):
        schema = self.read({"type": "array", "items": {"type": "string"}})
        self.assertEqual(schema.items.types, ("string",))
        self.assertEqual(schema.prefix_items, ())

    def test_array_items_is_tuple_validation(self):
        schema = self.read({"items": [{"type": "string"}, {"type": "integer"}]})
        self.assertIsNone(schema.items)
        self.assertEqual([s.types for s in schema.prefix_items],
                         [("string",), ("integer",)])

    def test_additional_items_becomes_items(self):
        schema = self.read({"items": [{"type": "string"}],
                            "additionalItems": {"type": "integer"}})
        self.assertEqual(schema.items.types, ("integer",))

    def test_prefix_items_wins(self):
        schema = self.read({"items": [{"type": "string"}],
                            "prefixItems": [{"type": "boolean"}]})
        self.assertEqual([s.types for s in schema.prefix_items], [("boolean",)])

    def test_constraints(self):
        schema = self.read({"type": "array", "minItems": 1, "maxItems": 3,
                            "uniqueItems": True})
        self.assertEqual(schema.array_constraints,
                         ArrayConstraints(min_items=1, max_items=3, unique_items=True))


class TestObjects(SchemaTestCase):
    def test_properties_and_required(self):
        schema = self.read({"type": "object", "required": ["a"],
                            "properties": {"a": {"type": "string"}}})
        self.assertEqual(schema.required, ("a",))
        self.assertEqual(schema.properties["a"].types, ("string",))

    def test_is_property_required(self):
        schema = self.read({"type": "object", "required": ["a"],
                            "properties": {"a": {"type": "string"},
                                           "b": {"type": "string"}}})
        self.assertTrue(schema.is_property_required("a"))
        self.assertFalse(schema.is_property_required("b"))
        self.assertFalse(schema.is_property_required("absent"))

    def test_additional_properties_as_bool(self):
        self.assertIs(self.read({"additionalProperties": False}).additional_properties, False)

    def test_additional_properties_as_schema(self):
        schema = self.read({"additionalProperties": {"type": "string"}})
        self.assertEqual(schema.additional_properties.types, ("string",))

    def test_absent_additional_properties_is_none(self):
        self.assertIsNone(self.read({"type": "object"}).additional_properties)

    def test_boolean_schemas(self):
        self.assertEqual(self.read(True), Schema())
        self.assertEqual(self.read(False), Schema(not_=Schema()))


class TestAnnotations(SchemaTestCase):
    def test_absent_default_is_unset(self):
        self.assertIs(self.read({"type": "string"}).default, UNSET)

    def test_null_default_is_kept(self):
        # `default: null` means the default *is* null - distinct from absent.
        self.assertIsNone(self.read({"default": None}).default)

    def test_singular_example(self):
        self.assertEqual(self.read({"example": "doggie"}).examples, ("doggie",))

    def test_examples_array_wins(self):
        self.assertEqual(self.read({"example": "old", "examples": ["new"]}).examples,
                         ("new",))

    def test_enum(self):
        self.assertEqual(self.read({"enum": ["a", "b"]}).enum, ("a", "b"))

    def test_flags(self):
        schema = self.read({"deprecated": True, "readOnly": True, "writeOnly": False})
        self.assertEqual((schema.deprecated, schema.read_only, schema.write_only),
                         (True, True, False))

    def test_const(self):
        self.assertEqual(self.read({"const": "dog"}).const, "dog")


class TestDiscriminator(SchemaTestCase):
    def test_2_0_string_form(self):
        self.assertEqual(self.read({"discriminator": "petType"}).discriminator,
                         Discriminator(property_name="petType"))

    def test_3_x_object_form(self):
        schema = self.read({"discriminator": {"propertyName": "petType",
                                              "mapping": {"dog": "#/c/Dog"}}})
        self.assertEqual(schema.discriminator,
                         Discriminator("petType", {"dog": "#/c/Dog"}))

    def test_missing_property_name_warns(self):
        schema, warnings = self.parse({"discriminator": {"mapping": {}}})
        self.assertIsNone(schema.discriminator)
        self.assertIn("propertyName", warnings[0].message)


class TestWarnings(SchemaTestCase):
    def test_unmodelled_keywords_are_silent(self):
        _, warnings = self.parse({"type": "object", "xml": {"name": "Pet"},
                                  "if": {"type": "string"}, "$schema": "https://x"})
        self.assertEqual(warnings, ())

    def test_malformed_modelled_keyword_warns(self):
        _, warnings = self.parse({"enum": "not-a-list", "minLength": "1"})
        self.assertEqual({w.pointer for w in warnings}, {"#/enum", "#/minLength"})

    def test_pointer_locates_nested_failure(self):
        _, warnings = self.parse({"properties": {"a": {"minLength": "1"}}})
        self.assertEqual(warnings[0].pointer, "#/properties/a/minLength")

    def test_non_object_schema_warns(self):
        schema, warnings = self.parse("nope")
        self.assertIsNone(schema)
        self.assertIn("expected an object", warnings[0].message)

    def test_unusable_property_is_dropped_not_fatal(self):
        schema, warnings = self.parse({"properties": {"good": {"type": "string"},
                                                      "bad": "nope"}})
        self.assertEqual(list(schema.properties), ["good"])
        self.assertEqual(len(warnings), 1)


class TestReadSchema(SchemaTestCase):
    """
    The entry point, over the whole Pet fixture.

    Each test asserts the complete model rather than sampling it, so anything
    invented, dropped or mistranslated fails here - including the `xml` that
    only the 2.0 flavour carries and that nothing models.
    """

    def testV2Parse(self):
        self.assertEqual(self.read(PET_V2), expected_pet("#/definitions/"))

    def testV30Parse(self):
        self.assertEqual(self.read(PET_V30), expected_pet("#/components/schemas/"))

    def testV31Parse(self):
        self.assertEqual(self.read(PET_V31), expected_pet("#/components/schemas/"))


if __name__ == "__main__":
    unittest.main()
