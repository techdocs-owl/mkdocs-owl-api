from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace

from mkdocs.structure.files import Files

from mkdocs_owl_api.plugin import OwlApiConfig, OwlApiPlugin, _normalize_frontmatter


def _fake_page(meta: dict, src_path: str, abs_src_path: str):
    """Minimal stand-in for a MkDocs Page (only the attributes the plugin uses)."""
    return SimpleNamespace(
        meta=meta,
        file=SimpleNamespace(src_path=src_path, abs_src_path=abs_src_path),
    )


def _plugin() -> OwlApiPlugin:
    plugin = OwlApiPlugin()
    plugin.config = OwlApiConfig()
    return plugin


class TestNormalizeFrontmatter(unittest.TestCase):
    def test_frontmatter_short_form(self):
        self.assertEqual(_normalize_frontmatter("./spec.yml"), {"spec": "./spec.yml"})

    def test_frontmatter_long_form(self):
        cfg = _normalize_frontmatter({"spec": "a.yml", "title": "T", "schema_depth": 4})
        self.assertEqual(cfg["spec"], "a.yml")
        self.assertEqual(cfg["title"], "T")
        self.assertEqual(cfg["schema_depth"], 4)

    def test_frontmatter_invalid(self):
        self.assertIsNone(_normalize_frontmatter(123))
        self.assertIsNone(_normalize_frontmatter({"title": "no spec"}))
        self.assertIsNone(_normalize_frontmatter({"spec": 5}))
        self.assertIsNone(_normalize_frontmatter(None))


class TestOwlApiConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = OwlApiConfig()
        self.assertEqual(cfg.schema_depth, 3)
        self.assertFalse(cfg.hide_internal)
        self.assertFalse(cfg.hide_bindings)
        self.assertFalse(cfg.hide_traits)
        self.assertFalse(cfg.hide_security)
        self.assertFalse(cfg.hide_version)
        self.assertFalse(cfg.hide_download_link)


class TestOnConfigAndOnFiles(unittest.TestCase):
    def test_css_register(self):
        plugin = _plugin()
        config = SimpleNamespace(extra_css=[])
        plugin.on_config(config)
        self.assertIn("assets/techdocs-owl-api.css", config.extra_css)

    def test_css_inject(self):
        plugin = _plugin()
        config = SimpleNamespace(
            site_dir="/tmp/site", use_directory_urls=True,
            plugins=SimpleNamespace(_current_plugin=None),
        )
        files = Files([])
        plugin.on_files(files, config=config)
        css_file = files.get_file_from_path("assets/techdocs-owl-api.css")
        self.assertIsNotNone(css_file)
        self.assertIn(".techdocs-owl-api-pill", css_file.content_string)


class TestOnPageMarkdownEndToEnd(unittest.TestCase):
    def _setup(self, t: str, meta: dict, spec_text: str, spec_name="spec.yml"):
        root = pathlib.Path(t)
        docs = root / "docs"
        site = root / "site"
        api = docs / "api"
        api.mkdir(parents=True)
        site.mkdir(parents=True)
        (api / spec_name).write_text(spec_text, encoding="utf-8")
        page = _fake_page(meta, "api/demo.md", str(api / "demo.md"))
        config = {"docs_dir": str(docs), "site_dir": str(site)}
        return root, page, config

    ASYNC = (
        "asyncapi: '2.6.0'\n"
        "info:\n  title: E2E\n  version: '1'\n"
        "channels:\n"
        "  c:\n"
        "    subscribe:\n"
        "      operationId: op\n"
        "      message:\n"
        "        name: m\n"
        "        payload:\n"
        "          type: object\n"
        "          properties:\n"
        "            id:\n"
        "              type: string\n"
    )

    def test_markdown_passthrough(self):
        plugin = _plugin()
        page = _fake_page({}, "api/demo.md", "/x/api/demo.md")
        out = plugin.on_page_markdown("HELLO", page=page, config={}, files=[])
        self.assertEqual(out, "HELLO")

    def test_asyncapi_spec_written(self):
        plugin = _plugin()
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(
                t, {"techdocs-owl-asyncapi": {"spec": "spec.yml"}}, self.ASYNC)
            out = plugin.on_page_markdown("orig", page=page, config=config, files=[])
            self.assertIn("# E2E", out)
            self.assertIn("## Operations", out)
            self.assertNotIn("## Channels", out)
            self.assertTrue((root / "docs/assets/techdocs-owl-api/demo.json").exists())
            self.assertTrue((root / "site/assets/techdocs-owl-api/demo.json").exists())
            self.assertIn("Specification Source", out)

    def test_openapi_render(self):
        plugin = _plugin()
        oas = json.dumps({
            "openapi": "3.0.3", "info": {"title": "OAS", "version": "1"},
            "paths": {"/p": {"get": {"summary": "g", "responses": {"200": {"description": "ok"}}}}},
        })
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(
                t, {"techdocs-owl-openapi": {"spec": "spec.json"}}, oas, spec_name="spec.json")
            out = plugin.on_page_markdown("orig", page=page, config=config, files=[])
            self.assertIn("# OAS", out)
            self.assertIn("`/p`", out)

    def test_render_invalid_frontmatter(self):
        plugin = _plugin()
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(t, {"techdocs-owl-asyncapi": 123}, self.ASYNC)
            out = plugin.on_page_markdown("orig", page=page, config=config, files=[])
            self.assertIn('!!! danger "invalid frontmatter"', out)

    def test_render_missing_spec(self):
        plugin = _plugin()
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(
                t, {"techdocs-owl-asyncapi": {"spec": "nope.yml"}}, self.ASYNC)
            out = plugin.on_page_markdown("orig", page=page, config=config, files=[])
            self.assertIn("spec file not found", out)

    def test_config_defaults(self):
        plugin = _plugin()
        plugin.config = OwlApiConfig()
        plugin.config.load_dict({"hide_version": True})
        plugin.config.validate()
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(
                t, {"techdocs-owl-asyncapi": {"spec": "spec.yml"}}, self.ASYNC)
            out = plugin.on_page_markdown("orig", page=page, config=config, files=[])
            self.assertNotIn("**Version:**", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
