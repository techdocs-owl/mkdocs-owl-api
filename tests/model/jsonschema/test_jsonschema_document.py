from __future__ import annotations

import unittest

from mkdocs_owl_api.model.jsonschema.types import JsonSchemaDialect, JsonSchemaDoc
from mkdocs_owl_api.model.jsonschema.parser import parse_document

from ...fixtures import SCHEMA_DOC_2020_12, SCHEMA_DOC_DRAFT04, expected_order

DRAFT04_URI = "http://json-schema.org/draft-04/schema#"
V2020_12_URI = "https://json-schema.org/draft/2020-12/schema"


class TestDialectDetection(unittest.TestCase):
    def read(self, raw):
        return parse_document(raw)

    def test_every_known_dialect(self):
        cases = {
            "http://json-schema.org/draft-04/schema#": JsonSchemaDialect.DRAFT_04,
            "http://json-schema.org/draft-06/schema#": JsonSchemaDialect.DRAFT_06,
            "http://json-schema.org/draft-07/schema#": JsonSchemaDialect.DRAFT_07,
            "https://json-schema.org/draft/2019-09/schema": (
                JsonSchemaDialect.DRAFT_2019_09),
            "https://json-schema.org/draft/2020-12/schema": (
                JsonSchemaDialect.DRAFT_2020_12),
        }
        for uri, dialect in cases.items():
            with self.subTest(uri=uri):
                result = self.read({"$schema": uri})
                self.assertEqual(result.doc.dialect, dialect)
                self.assertEqual(result.doc.spec_version, uri)
                self.assertEqual(result.warnings, ())

    def test_unknown_dialect_reads_as_newest_and_warns(self):
        result = self.read({"$schema": "https://example.test/whatever"})
        self.assertEqual(result.doc.dialect, JsonSchemaDialect.DRAFT_2020_12)
        self.assertEqual(result.doc.spec_version, "https://example.test/whatever")
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("unknown `$schema`", result.warnings[0].message)

    def test_missing_dialect_reads_as_newest_and_warns(self):
        result = self.read({"type": "object"})
        self.assertEqual(result.doc.dialect, JsonSchemaDialect.DRAFT_2020_12)
        self.assertEqual(result.doc.spec_version, "")
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("no `$schema`", result.warnings[0].message)

    def test_a_non_object_is_not_fatal(self):
        result = self.read(["not", "a", "schema"])
        self.assertEqual(result.doc, JsonSchemaDoc())
        self.assertIn("expected an object", result.warnings[0].message)


class TestIdentity(unittest.TestCase):
    def test_dollar_id(self):
        doc = parse_document({"$id": "https://example.test/a.json"}).doc
        self.assertEqual(doc.schema_id, "https://example.test/a.json")

    def test_draft_04_spells_it_without_the_dollar(self):
        doc = parse_document({"$schema": DRAFT04_URI,
                              "id": "https://example.test/a.json"}).doc
        self.assertEqual(doc.schema_id, "https://example.test/a.json")

    def test_absent(self):
        self.assertIsNone(parse_document({"$schema": V2020_12_URI}).doc.schema_id)


class TestDefinitions(unittest.TestCase):
    def test_both_spellings_are_read(self):
        for key in ("definitions", "$defs"):
            with self.subTest(key=key):
                doc = parse_document(
                    {"$schema": V2020_12_URI, key: {"A": {"type": "string"}}}).doc
                self.assertEqual(list(doc.definitions), ["A"])
                self.assertEqual(doc.definitions["A"].types, ("string",))

    def test_defs_wins_a_collision(self):
        doc = parse_document({
            "$schema": V2020_12_URI,
            "definitions": {"A": {"type": "string"}, "B": {"type": "boolean"}},
            "$defs": {"A": {"type": "integer"}},
        }).doc
        self.assertEqual(doc.definitions["A"].types, ("integer",))
        self.assertEqual(doc.definitions["B"].types, ("boolean",))

    def test_an_unusable_definition_costs_only_itself(self):
        result = parse_document({
            "$schema": V2020_12_URI,
            "$defs": {"good": {"type": "string"}, "bad": 7},
        })
        self.assertEqual(list(result.doc.definitions), ["good"])
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.warnings[0].pointer, "#/$defs/bad")


class TestInfoSynthesis(unittest.TestCase):
    def test_title_and_description_come_from_the_root(self):
        doc = parse_document({
            "$schema": V2020_12_URI, "title": "Order", "description": "An order.",
        }).doc
        self.assertEqual(doc.info.title, "Order")
        self.assertEqual(doc.info.description, "An order.")

    def test_what_a_schema_never_states_stays_empty(self):
        doc = parse_document({"$schema": V2020_12_URI, "title": "Order"}).doc
        self.assertEqual(doc.info.version, "")
        self.assertIsNone(doc.info.license)
        self.assertIsNone(doc.info.contact)

    def test_the_document_is_itself_the_root_schema(self):
        doc = parse_document({
            "$schema": V2020_12_URI, "type": "object",
            "properties": {"a": {"type": "string"}}, "required": ["a"],
        }).doc
        self.assertEqual(doc.root.types, ("object",))
        self.assertEqual(list(doc.root.properties), ["a"])
        self.assertEqual(doc.root.required, ("a",))


class TestDialectIndependence(unittest.TestCase):
    def test_draft_04(self):
        result = parse_document(SCHEMA_DOC_DRAFT04)
        self.assertEqual(result.warnings, ())
        self.assertEqual(result.doc, expected_order(
            JsonSchemaDialect.DRAFT_04, DRAFT04_URI, "#/definitions/"))

    def test_2020_12(self):
        result = parse_document(SCHEMA_DOC_2020_12)
        self.assertEqual(result.warnings, ())
        self.assertEqual(result.doc, expected_order(
            JsonSchemaDialect.DRAFT_2020_12, V2020_12_URI, "#/$defs/"))


if __name__ == "__main__":
    unittest.main()
