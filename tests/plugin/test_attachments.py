from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
import warnings
from types import SimpleNamespace

from mkdocs.structure.files import Files

from mkdocs_owl_api import attachments
from mkdocs_owl_api.options import Attachment


def _fake_page(src_path: str, abs_src_path: str):
    """Minimal stand-in for a MkDocs Page (only the attributes the registrar uses)."""
    return SimpleNamespace(file=SimpleNamespace(
        src_path=src_path, src_uri=src_path, abs_src_path=abs_src_path))


def _fake_config(site_dir: pathlib.Path):
    """Minimal stand-in for MkDocsConfig (only what `File.generated` reads)."""
    return SimpleNamespace(
        site_dir=str(site_dir), use_directory_urls=True,
        plugins=SimpleNamespace(_current_plugin=None),
    )


class TestSaveSpec(unittest.TestCase):
    def test_spec_registered(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            docs = root / "docs"
            api = docs / "api"
            api.mkdir(parents=True)
            page = _fake_page("api/demo.md", str(api / "demo.md"))
            config = _fake_config(root / "site")
            files = Files([])
            link = attachments._save_spec({"info": {"title": "X"}}, page, config, files)
            self.assertIn("assets/techdocs-owl-api/demo.json", link)

            generated = files.get_file_from_path("assets/techdocs-owl-api/demo.json")
            self.assertIsNotNone(generated)
            self.assertEqual(json.loads(generated.content_string), {"info": {"title": "X"}})
            # docs_dir must stay untouched - nothing written into the user's sources
            self.assertFalse((docs / "assets").exists())

    def test_spec_replaces_existing_entry(self):
        """A rebuilt page re-registers the same path; that must not warn or duplicate."""
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            api = root / "docs/api"
            api.mkdir(parents=True)
            page = _fake_page("api/demo.md", str(api / "demo.md"))
            config = _fake_config(root / "site")
            files = Files([])
            attachments._save_spec({"info": {"title": "X"}}, page, config, files)
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                attachments._save_spec({"info": {"title": "Y"}}, page, config, files)
            generated = files.get_file_from_path("assets/techdocs-owl-api/demo.json")
            self.assertEqual(json.loads(generated.content_string), {"info": {"title": "Y"}})


class TestSaveAttachments(unittest.TestCase):
    def test_attachments_registered(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            docs = root / "docs"
            api = docs / "api"
            api.mkdir(parents=True)
            (api / "schema.proto").write_text("syntax=proto3;", encoding="utf-8")
            page = _fake_page("api/demo.md", str(api / "demo.md"))
            config = _fake_config(root / "site")
            files = Files([])
            declared = [
                Attachment(path="schema.proto", title="Proto",
                           description="Payload schemas"),
                Attachment(path="missing.proto"),
            ]
            results = attachments._save_attachments(declared, page, config, files)
            self.assertEqual(results[0].title, "Proto")
            self.assertEqual(results[0].description, "Payload schemas")
            self.assertIsNotNone(results[0].url)

            generated = files.get_file_from_path("assets/techdocs-owl-api/demo-schema.proto")
            self.assertIsNotNone(generated)
            self.assertEqual(generated.content_bytes, b"syntax=proto3;")
            self.assertFalse((docs / "assets").exists())

            self.assertIsNone(results[1].url)
            self.assertIsNotNone(results[1].error)
            self.assertEqual(results[1].description, "")
            self.assertIsNone(
                files.get_file_from_path("assets/techdocs-owl-api/demo-missing.proto"))

    def test_attachment_shorthand_has_no_description(self):
        """The bare-string form still works; it just has nothing to describe."""
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            api = root / "docs/api"
            api.mkdir(parents=True)
            (api / "schema.proto").write_text("syntax=proto3;", encoding="utf-8")
            page = _fake_page("api/demo.md", str(api / "demo.md"))
            results = attachments._save_attachments(
                [Attachment(path="schema.proto")], page,
                _fake_config(root / "site"), Files([]))
            self.assertEqual(results[0].title, "schema.proto")
            self.assertEqual(results[0].description, "")

    def test_url_attachment_name_drops_the_query_string(self):
        """The output filename comes off the URI path, not off `item.path`."""
        self.assertEqual(
            attachments._filename("https://ex.com/p/schema.proto?v=2"), "schema.proto")


if __name__ == "__main__":
    unittest.main(verbosity=2)
