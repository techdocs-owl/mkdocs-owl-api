from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
import warnings
from types import SimpleNamespace

from mkdocs.structure.files import Files

from mkdocs_owl_api import loader
from mkdocs_owl_api.loader import SpecError
from mkdocs_owl_api.options import Attachment


def _fake_page(src_path: str, abs_src_path: str):
    """Minimal stand-in for a MkDocs Page (only the attributes the loader uses)."""
    return SimpleNamespace(file=SimpleNamespace(src_path=src_path, abs_src_path=abs_src_path))


def _fake_config(site_dir: pathlib.Path):
    """Minimal stand-in for MkDocsConfig (only what `File.generated` reads)."""
    return SimpleNamespace(
        site_dir=str(site_dir), use_directory_urls=True,
        plugins=SimpleNamespace(_current_plugin=None),
    )


class TestLoadSpec(unittest.TestCase):
    def _write(self, d: pathlib.Path, name: str, content: str) -> pathlib.Path:
        p = d / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_valid_yaml(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "s.yml", "asyncapi: '3.0.0'\ninfo:\n  title: X\n  version: '1'\n")
            spec = loader._load_spec("s.yml", d)
            self.assertEqual(spec["info"]["title"], "X")

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "s.json", json.dumps({"openapi": "3.0.3", "info": {"title": "J"}}))
            spec = loader._load_spec("s.json", d)
            self.assertEqual(spec["info"]["title"], "J")

    def test_not_found(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SpecError) as ctx:
                loader._load_spec("missing.yml", pathlib.Path(t))
            self.assertIn("spec file not found", str(ctx.exception))

    def test_empty(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "e.yml", "")
            with self.assertRaises(SpecError) as ctx:
                loader._load_spec("e.yml", d)
            self.assertIn("spec file is empty", str(ctx.exception))

    def test_not_a_mapping(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "list.yml", "- a\n- b\n")
            with self.assertRaises(SpecError) as ctx:
                loader._load_spec("list.yml", d)
            self.assertIn("unexpected spec content", str(ctx.exception))

    def test_parse_error(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "bad.yml", "a: b:\n  - : :\n::::\n")
            with self.assertRaises(SpecError) as ctx:
                loader._load_spec("bad.yml", d)
            self.assertIn("spec parse error", str(ctx.exception))


class TestResolveExternalRefs(unittest.TestCase):
    def test_refs_local_inline(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            (d / "child.yml").write_text(
                "type: object\nproperties:\n  x:\n    type: string\n", encoding="utf-8")
            node = {"payload": {"$ref": "child.yml"}}
            loader._resolve_external_refs(node, str(d / "main.yml"))
            self.assertNotIn("$ref", node["payload"])
            self.assertEqual(node["payload"]["type"], "object")
            self.assertIn("x", node["payload"]["properties"])

    def test_refs_internal(self):
        node = {"a": {"$ref": "#/components/schemas/Foo"}}
        loader._resolve_external_refs(node, "/tmp/main.yml")
        self.assertEqual(node["a"]["$ref"], "#/components/schemas/Foo")


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
            link = loader._save_spec({"info": {"title": "X"}}, page, config, files)
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
            loader._save_spec({"info": {"title": "X"}}, page, config, files)
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                loader._save_spec({"info": {"title": "Y"}}, page, config, files)
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
            attachments = [
                Attachment(path="schema.proto", title="Proto",
                           description="Payload schemas"),
                Attachment(path="missing.proto"),
            ]
            results = loader._save_attachments(attachments, page, config, files)
            self.assertEqual(results[0]["title"], "Proto")
            self.assertEqual(results[0]["description"], "Payload schemas")
            self.assertIsNotNone(results[0]["url"])

            generated = files.get_file_from_path("assets/techdocs-owl-api/demo-schema.proto")
            self.assertIsNotNone(generated)
            self.assertEqual(generated.content_bytes, b"syntax=proto3;")
            self.assertFalse((docs / "assets").exists())

            self.assertIsNone(results[1]["url"])
            self.assertIsNotNone(results[1]["error"])
            self.assertEqual(results[1]["description"], "")
            self.assertIsNone(files.get_file_from_path("assets/techdocs-owl-api/demo-missing.proto"))

    def test_attachment_shorthand_has_no_description(self):
        """The bare-string form still works; it just has nothing to describe."""
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            api = root / "docs/api"
            api.mkdir(parents=True)
            (api / "schema.proto").write_text("syntax=proto3;", encoding="utf-8")
            page = _fake_page("api/demo.md", str(api / "demo.md"))
            results = loader._save_attachments(
                [Attachment(path="schema.proto")], page,
                _fake_config(root / "site"), Files([]))
            self.assertEqual(results[0]["title"], "schema.proto")
            self.assertEqual(results[0]["description"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
