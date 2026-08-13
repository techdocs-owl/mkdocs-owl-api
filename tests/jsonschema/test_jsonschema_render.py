from __future__ import annotations

import re
import unittest

from mkdocs_owl_api.common.render import RenderContext
from mkdocs_owl_api.jsonschema import Renderer, parse_document
from mkdocs_owl_api.options import PageOptions

from ..fixtures import SCHEMA_DOC_2020_12, SCHEMA_DOC_DRAFT04

V2020_12_URI = "https://json-schema.org/draft/2020-12/schema"


def render(spec, **options):
    return Renderer(parse_document(spec).doc, RenderContext(
        options=PageOptions(type="jsonschema", **options),
    )).render()


class TestPreamble(unittest.TestCase):
    def test_title_comes_from_the_root(self):
        self.assertIn("# Order", render(SCHEMA_DOC_2020_12))

    def test_title_option_wins(self):
        page = render(SCHEMA_DOC_2020_12, title="Ordering API")
        self.assertIn("# Ordering API", page)
        self.assertNotIn("# Order\n", page)

    def test_specification_line_names_the_dialect_not_the_uri(self):
        self.assertIn("**Specification:** `json-schema 2020-12`",
                      render(SCHEMA_DOC_2020_12))
        self.assertIn("**Specification:** `json-schema draft-04`",
                      render(SCHEMA_DOC_DRAFT04))
        self.assertNotIn(V2020_12_URI, render(SCHEMA_DOC_2020_12))

    def test_schema_id_is_stated(self):
        self.assertIn("**Schema ID:** `https://example.test/order.schema.json`",
                      render(SCHEMA_DOC_2020_12))

    def test_no_schema_id_no_line(self):
        self.assertNotIn("**Schema ID:**", render({"$schema": V2020_12_URI}))

    def test_the_root_description_appears_once(self):
        """It reaches the preamble via the synthesised `info`, not twice."""
        page = render(SCHEMA_DOC_2020_12)
        self.assertEqual(page.count("An order placed against the catalogue."), 1)

    def test_a_schema_states_no_version_so_no_version_line(self):
        self.assertNotIn("**Version:**", render(SCHEMA_DOC_2020_12))


class TestSections(unittest.TestCase):
    def test_root_and_definitions(self):
        page = render(SCHEMA_DOC_2020_12)
        self.assertIn("## Schema", page)
        self.assertIn("## Definitions", page)
        self.assertLess(page.index("## Schema"), page.index("## Definitions"))

    def test_each_definition_gets_a_heading(self):
        page = render(SCHEMA_DOC_2020_12)
        self.assertIn("### Customer {#schemas-customer}", page)
        self.assertIn("### Line {#schemas-line}", page)

    def test_a_document_with_no_root_worth_showing_omits_the_section(self):
        page = render({"$schema": V2020_12_URI,
                       "$defs": {"A": {"type": "string"}}})
        self.assertNotIn("## Schema", page)
        self.assertIn("## Definitions", page)

    def test_a_document_with_no_definitions_omits_that_section(self):
        page = render({"$schema": V2020_12_URI, "type": "object",
                       "properties": {"a": {"type": "string"}}})
        self.assertIn("## Schema", page)
        self.assertNotIn("## Definitions", page)

    def test_the_root_property_table_is_rendered(self):
        page = render(SCHEMA_DOC_2020_12)
        self.assertIn("techdocs-owl-api-prop", page)
        self.assertIn("Opaque order identifier.", page)


class TestReferences(unittest.TestCase):
    def test_a_ref_links_to_the_definition_heading(self):
        page = render(SCHEMA_DOC_2020_12)
        self.assertIn('href="#schemas-customer"', page)
        self.assertIn('href="#schemas-line"', page)

    def test_every_reference_resolves_to_an_anchor_on_the_page(self):
        for name, spec in (("2020-12", SCHEMA_DOC_2020_12),
                           ("draft-04", SCHEMA_DOC_DRAFT04)):
            with self.subTest(dialect=name):
                page = render(spec)
                anchors = set(re.findall(r"\{#([a-z0-9-]+)\}", page))
                links = set(re.findall(r'href="#(schemas-[a-z0-9-]+)"', page))
                self.assertTrue(links)
                self.assertEqual(links - anchors, set())

    def test_both_dialects_render_identically(self):
        self.assertEqual(
            render(SCHEMA_DOC_2020_12).replace("2020-12", "draft-04"),
            render(SCHEMA_DOC_DRAFT04),
        )


class TestOptions(unittest.TestCase):
    def test_hide_internal_drops_marked_properties(self):
        spec = {
            "$schema": V2020_12_URI, "type": "object",
            "properties": {
                "shown": {"type": "string"},
                "hidden": {"type": "string", "x-internal-only": True},
            },
        }
        self.assertIn("hidden", render(spec))
        self.assertNotIn("hidden", render(spec, hide_internal=True))

    def test_schema_depth_limits_nesting(self):
        spec = {
            "$schema": V2020_12_URI, "type": "object",
            "properties": {"a": {"type": "object", "properties": {
                "b": {"type": "object", "properties": {"c": {"type": "string"}}}}}},
        }
        def paths(depth):
            return render(spec, schema_depth=depth).replace("<wbr>", "")

        self.assertIn("a.b.</span>", paths(3))
        self.assertNotIn("a.b.</span>", paths(1))


if __name__ == "__main__":
    unittest.main()
