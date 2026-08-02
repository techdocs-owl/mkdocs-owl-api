from __future__ import annotations

import unittest

from mkdocs_owl_api.options import Attachment, PageOptions, site_default


class TestResolve(unittest.TestCase):
    def test_defaults(self):
        opts = PageOptions.resolve()
        self.assertEqual(opts.schema_depth, 3)
        self.assertEqual(opts.spec, "")
        self.assertEqual(opts.attachments, ())
        self.assertFalse(opts.hide_internal)

    def test_frontmatter_overrides_site_defaults(self):
        opts = PageOptions.resolve(
            {"schema_depth": 3, "hide_traits": False},
            {"spec": "a.yml", "schema_depth": 5, "hide_traits": True},
        )
        self.assertEqual(opts.spec, "a.yml")
        self.assertEqual(opts.schema_depth, 5)
        self.assertTrue(opts.hide_traits)

    def test_site_defaults_apply_when_page_is_silent(self):
        opts = PageOptions.resolve({"hide_bindings": True}, {"spec": "a.yml"})
        self.assertTrue(opts.hide_bindings)

    def test_unknown_keys_are_ignored(self):
        opts = PageOptions.resolve({}, {"spec": "a.yml", "nonsense": 1})
        self.assertEqual(opts.spec, "a.yml")

    def test_frozen(self):
        opts = PageOptions.resolve()
        with self.assertRaises(Exception):
            opts.schema_depth = 9  # type: ignore[misc]


class TestCoercion(unittest.TestCase):
    def test_schema_depth_clamped_and_defaulted(self):
        self.assertEqual(PageOptions.resolve({}, {"schema_depth": 0}).schema_depth, 1)
        self.assertEqual(PageOptions.resolve({}, {"schema_depth": -4}).schema_depth, 1)
        self.assertEqual(PageOptions.resolve({}, {"schema_depth": "x"}).schema_depth, 3)
        self.assertEqual(PageOptions.resolve({}, {"schema_depth": "7"}).schema_depth, 7)

    def test_schema_depth_rejects_bool(self):
        """`isinstance(True, int)` holds, so `schema_depth: true` must not become depth 1."""
        self.assertEqual(PageOptions.resolve({}, {"schema_depth": True}).schema_depth, 3)

    def test_quoted_false_is_falsey(self):
        """The bug plain `bool(opts.get(...))` had: a quoted "false" flipped the flag on."""
        for value in ("false", "False", " no ", "off", "0", ""):
            with self.subTest(value=value):
                self.assertFalse(PageOptions.resolve({}, {"hide_internal": value}).hide_internal)

    def test_truthy_strings(self):
        for value in ("true", "TRUE", "yes", "on", "1"):
            with self.subTest(value=value):
                self.assertTrue(PageOptions.resolve({}, {"hide_internal": value}).hide_internal)

    def test_unparseable_bool_falls_back(self):
        self.assertFalse(PageOptions.resolve({}, {"hide_internal": "maybe"}).hide_internal)
        self.assertFalse(PageOptions.resolve({}, {"hide_internal": None}).hide_internal)

    def test_strings_are_stripped(self):
        opts = PageOptions.resolve({}, {"spec": "  a.yml  ", "title": " T "})
        self.assertEqual(opts.spec, "a.yml")
        self.assertEqual(opts.title, "T")

    def test_attachments_parsed_to_dataclasses(self):
        self.assertEqual(
            PageOptions.resolve({}, {"attachments": ["a", "b"]}).attachments,
            (Attachment(path="a"), Attachment(path="b")))

    def test_attachment_mapping_form(self):
        opts = PageOptions.resolve({}, {"attachments": [
            {"path": "x.proto", "title": "Proto", "description": "Wire format"},
        ]})
        self.assertEqual(
            opts.attachments,
            (Attachment(path="x.proto", title="Proto", description="Wire format"),))

    def test_attachment_mapping_defaults(self):
        opts = PageOptions.resolve({}, {"attachments": [{"path": "x.proto"}]})
        self.assertEqual(opts.attachments[0].title, "")
        self.assertEqual(opts.attachments[0].description, "")

    def test_malformed_attachment_entries_are_dropped(self):
        opts = PageOptions.resolve({}, {"attachments": [
            "keep.proto", 123, {"title": "no path"}, {"path": 5}, None,
        ]})
        self.assertEqual(opts.attachments, (Attachment(path="keep.proto"),))

    def test_attachments_not_a_list(self):
        self.assertEqual(PageOptions.resolve({}, {"attachments": "nope"}).attachments, ())
        self.assertEqual(PageOptions.resolve({}, {"attachments": None}).attachments, ())

    def test_attachment_is_frozen(self):
        att = Attachment(path="a")
        with self.assertRaises(Exception):
            att.path = "b"  # type: ignore[misc]


class TestType(unittest.TestCase):
    def test_type_is_carried_and_lowercased(self):
        self.assertEqual(PageOptions.resolve({}, {"type": "  AsyncAPI "}).type, "asyncapi")

    def test_type_defaults_to_empty(self):
        self.assertEqual(PageOptions.resolve().type, "")

    def test_event_driven_flags_present_regardless_of_type(self):
        """One flat class - the OpenAPI renderer simply never reads these."""
        opts = PageOptions.resolve({}, {"type": "openapi", "hide_bindings": True})
        self.assertTrue(opts.hide_bindings)


class TestSiteDefault(unittest.TestCase):
    def test_matches_dataclass_fields(self):
        self.assertEqual(site_default("schema_depth"), 3)
        self.assertIs(site_default("hide_traits"), False)

    def test_unknown_key(self):
        with self.assertRaises(KeyError):
            site_default("nope")


if __name__ == "__main__":
    unittest.main(verbosity=2)
