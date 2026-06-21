from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace

from mkdocs_owl_api import loader


def _fake_page(src_path: str, abs_src_path: str):
    """Minimal stand-in for a MkDocs Page (only the attributes the loader uses)."""
    return SimpleNamespace(file=SimpleNamespace(src_path=src_path, abs_src_path=abs_src_path))


class TestLoadSpec(unittest.TestCase):
    def _write(self, d: pathlib.Path, name: str, content: str) -> pathlib.Path:
        p = d / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_valid_yaml(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "s.yml", "asyncapi: '3.0.0'\ninfo:\n  title: X\n  version: '1'\n")
            spec, err = loader._load_spec("s.yml", d)
            self.assertIsNone(err)
            self.assertEqual(spec["info"]["title"], "X")

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "s.json", json.dumps({"openapi": "3.0.3", "info": {"title": "J"}}))
            spec, err = loader._load_spec("s.json", d)
            self.assertIsNone(err)
            self.assertEqual(spec["info"]["title"], "J")

    def test_not_found(self):
        with tempfile.TemporaryDirectory() as t:
            spec, err = loader._load_spec("missing.yml", pathlib.Path(t))
            self.assertIsNone(spec)
            self.assertIn("spec file not found", err)

    def test_empty(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "e.yml", "")
            spec, err = loader._load_spec("e.yml", d)
            self.assertIsNone(spec)
            self.assertIn("spec file is empty", err)

    def test_not_a_mapping(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "list.yml", "- a\n- b\n")
            spec, err = loader._load_spec("list.yml", d)
            self.assertIsNone(spec)
            self.assertIn("unexpected spec content", err)

    def test_parse_error(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "bad.yml", "a: b:\n  - : :\n::::\n")
            spec, err = loader._load_spec("bad.yml", d)
            self.assertIsNone(spec)
            self.assertIn("spec parse error", err)


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
    def test_spec_written(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            docs = root / "docs"
            site = root / "site"
            api = docs / "api"
            api.mkdir(parents=True)
            site.mkdir(parents=True)
            page = _fake_page("api/demo.md", str(api / "demo.md"))
            config = {"docs_dir": str(docs), "site_dir": str(site)}
            link = loader._save_spec({"info": {"title": "X"}}, page, config)
            self.assertTrue((docs / "assets/techdocs-owl-api/demo.json").exists())
            self.assertTrue((site / "assets/techdocs-owl-api/demo.json").exists())
            self.assertIn("assets/techdocs-owl-api/demo.json", link)


class TestSaveAttachments(unittest.TestCase):
    def test_attachments_copied(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            docs = root / "docs"
            site = root / "site"
            api = docs / "api"
            api.mkdir(parents=True)
            site.mkdir(parents=True)
            (api / "schema.proto").write_text("syntax=proto3;", encoding="utf-8")
            page = _fake_page("api/demo.md", str(api / "demo.md"))
            config = {"docs_dir": str(docs), "site_dir": str(site)}
            opts = {"attachments": [{"path": "schema.proto", "title": "Proto"},
                                    {"path": "missing.proto"}]}
            results = loader._save_attachments(opts, page, config)
            self.assertEqual(results[0]["title"], "Proto")
            self.assertIsNotNone(results[0]["url"])
            self.assertTrue((docs / "assets/techdocs-owl-api/demo-schema.proto").exists())
            self.assertTrue((site / "assets/techdocs-owl-api/demo-schema.proto").exists())
            self.assertIsNone(results[1]["url"])
            self.assertIsNotNone(results[1]["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
