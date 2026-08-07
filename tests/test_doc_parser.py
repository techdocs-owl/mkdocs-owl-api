from __future__ import annotations

import unittest

from mkdocs_owl_api.common.doc_model import Contact, ExternalDocs, License, Tag
from mkdocs_owl_api.common.doc_parser import (
    read_contact,
    read_external_docs,
    read_info,
    read_license,
    read_tags,
)
from mkdocs_owl_api.common.parse_report import Reporter


def parse(reader, raw):
    report = Reporter()
    return reader(raw, report), report.warnings


class TestInfo(unittest.TestCase):
    def test_full(self):
        info, warnings = parse(read_info, {
            "title": "Petstore", "version": "1.0.0",
            "summary": "Pets, mostly.",
            "description": "Long form.",
            "termsOfService": "https://example.test/tos",
            "contact": {"name": "Team", "email": "team@example.test"},
            "license": {"name": "MIT", "identifier": "MIT"},
            "x-logo": {"url": "https://example.test/logo.png"},
        })
        self.assertEqual(warnings, ())
        self.assertEqual((info.title, info.version), ("Petstore", "1.0.0"))
        self.assertEqual(info.summary, "Pets, mostly.")
        self.assertEqual(info.contact, Contact(name="Team", email="team@example.test"))
        self.assertEqual(info.license, License(name="MIT", identifier="MIT"))
        self.assertEqual(info.extensions, {"x-logo": {"url": "https://example.test/logo.png"}})

    def test_newer_only_fields_are_just_absent(self):
        # `summary` and `license.identifier` are 3.1-only; a 2.0 document simply
        # has no such keys, which needs no dialect awareness to handle.
        info, warnings = parse(read_info, {"title": "P", "version": "1"})
        self.assertEqual(warnings, ())
        self.assertIsNone(info.summary)

    def test_missing_info_warns_but_still_renders(self):
        info, warnings = parse(read_info, None)
        self.assertEqual(info.title, "")
        self.assertEqual(len(warnings), 1)

    def test_missing_title_and_version_warn(self):
        info, warnings = parse(read_info, {})
        self.assertEqual((info.title, info.version), ("", ""))
        self.assertEqual(len(warnings), 2)

    def test_wrong_typed_title_warns_once(self):
        info, warnings = parse(read_info, {"title": 7, "version": "1"})
        self.assertEqual(info.title, "")
        self.assertEqual([w.pointer for w in warnings], ["#/title", "#"])


class TestContactAndLicense(unittest.TestCase):
    def test_empty_contact_is_none(self):
        self.assertIsNone(parse(read_contact, {})[0])

    def test_absent_is_none_and_silent(self):
        self.assertEqual(parse(read_contact, None), (None, ()))

    def test_non_object_warns(self):
        contact, warnings = parse(read_contact, "team@example.test")
        self.assertIsNone(contact)
        self.assertIn("expected an object", warnings[0].message)

    def test_license_url_and_identifier_both_kept(self):
        # The spec calls these mutually exclusive; keeping both and letting the
        # renderer choose beats discarding what the author wrote.
        license_, warnings = parse(read_license,
                                   {"name": "MIT", "identifier": "MIT",
                                    "url": "https://example.test/mit"})
        self.assertEqual(warnings, ())
        self.assertEqual(license_.url, "https://example.test/mit")


class TestExternalDocs(unittest.TestCase):
    def test_url_and_description(self):
        docs, _ = parse(read_external_docs,
                        {"url": "https://example.test", "description": "More"})
        self.assertEqual(docs, ExternalDocs(url="https://example.test", description="More"))

    def test_description_without_url_warns(self):
        docs, warnings = parse(read_external_docs, {"description": "More"})
        self.assertEqual(docs.url, "")
        self.assertIn("cannot be followed", warnings[0].message)

    def test_empty_is_none(self):
        self.assertEqual(parse(read_external_docs, {}), (None, ()))


class TestTags(unittest.TestCase):
    def test_reads_each(self):
        tags, warnings = parse(read_tags, [
            {"name": "pets", "description": "Pet ops"},
            {"name": "store", "externalDocs": {"url": "https://example.test"}},
        ])
        self.assertEqual(warnings, ())
        self.assertEqual(tags[0], Tag(name="pets", description="Pet ops"))
        self.assertEqual(tags[1].external_docs.url, "https://example.test")

    def test_nameless_tag_is_dropped(self):
        tags, warnings = parse(read_tags, [{"description": "no name"}])
        self.assertEqual(tags, ())
        self.assertEqual(warnings[0].pointer, "#/0")

    def test_one_bad_entry_keeps_the_others(self):
        tags, warnings = parse(read_tags, ["nope", {"name": "pets"}])
        self.assertEqual([t.name for t in tags], ["pets"])
        self.assertEqual(len(warnings), 1)

    def test_absent_is_empty(self):
        self.assertEqual(parse(read_tags, None), ((), ()))


if __name__ == "__main__":
    unittest.main()
