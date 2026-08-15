from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace

from mkdocs.structure.files import Files

from mkdocs_owl_api.plugin import OwlApiConfig, OwlApiPlugin, _error_page


def _fake_page(meta: dict, src_path: str, abs_src_path: str):
    """Minimal stand-in for a MkDocs Page (only the attributes the plugin uses)."""
    return SimpleNamespace(
        meta=meta,
        file=SimpleNamespace(
            src_path=src_path, src_uri=src_path, abs_src_path=abs_src_path),
    )


def _plugin() -> OwlApiPlugin:
    plugin = OwlApiPlugin()
    plugin.config = OwlApiConfig()
    return plugin


class TestErrorPage(unittest.TestCase):
    def test_error_page(self):
        out = _error_page("spec parse error", "boom")
        self.assertIn('!!! danger "spec parse error"', out)
        self.assertIn("boom", out)


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
        config = SimpleNamespace(
            site_dir=str(site), use_directory_urls=True,
            plugins=SimpleNamespace(_current_plugin=None),
        )
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
            files = Files([])
            root, page, config = self._setup(
                t, {"techdocs-owl": {"type": "asyncapi", "spec": "spec.yml"}}, self.ASYNC)
            out = plugin.on_page_markdown("orig", page=page, config=config, files=files)
            self.assertIn("# E2E", out)
            self.assertIn("## Operations", out)
            self.assertNotIn("## Channels", out)
            self.assertIn("Specification Source", out)
            # the spec joins the build as a generated file, keeping --strict happy
            self.assertIsNotNone(files.get_file_from_path("assets/techdocs-owl-api/demo.json"))
            self.assertFalse((root / "docs/assets").exists())

    def test_openapi_render(self):
        plugin = _plugin()
        oas = json.dumps({
            "openapi": "3.0.3", "info": {"title": "OAS", "version": "1"},
            "paths": {"/p": {"get": {"summary": "g", "responses": {"200": {"description": "ok"}}}}},
        })
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(
                t, {"techdocs-owl": {"type": "openapi", "spec": "spec.json"}}, oas, spec_name="spec.json")
            out = plugin.on_page_markdown("orig", page=page, config=config, files=Files([]))
            self.assertIn("# OAS", out)
            self.assertIn("`/p`", out)

    def test_jsonschema_render(self):
        schema = json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Order", "type": "object",
            "properties": {"customer": {"$ref": "#/$defs/Customer"}},
            "$defs": {"Customer": {"type": "object",
                                   "properties": {"email": {"type": "string"}}}},
        })
        plugin = _plugin()
        with tempfile.TemporaryDirectory() as t:
            files = Files([])
            root, page, config = self._setup(
                t, {"techdocs-owl": {"type": "jsonschema", "spec": "spec.json"}},
                schema, spec_name="spec.json")
            out = plugin.on_page_markdown("orig", page=page, config=config, files=files)
            self.assertIn("# Order", out)
            self.assertIn("**Specification:** `json-schema 2020-12`", out)
            self.assertIn("### Customer {#schemas-customer}", out)
            # The reference reaches the heading rendered above it.
            self.assertIn('href="#schemas-customer"', out)
            # The schema joins the build as a generated file, like any other spec.
            self.assertIsNotNone(
                files.get_file_from_path("assets/techdocs-owl-api/demo.json"))
            self.assertFalse((root / "docs/assets").exists())

    def test_non_string_spec_is_coerced_then_not_found(self):
        """`spec:` is unvalidated - it is stringified, so the loader reports the miss."""
        for spec in (123, ["a.yml"]):
            with self.subTest(spec=spec):
                out = self._run({"techdocs-owl": {"type": "asyncapi", "spec": spec}})
                self.assertIn("spec file not found", out)

    def test_render_missing_spec(self):
        plugin = _plugin()
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(
                t, {"techdocs-owl": {"type": "asyncapi", "spec": "nope.yml"}}, self.ASYNC)
            out = plugin.on_page_markdown("orig", page=page, config=config, files=Files([]))
            self.assertIn("spec file not found", out)

    def test_old_keys_no_longer_recognised(self):
        plugin = _plugin()
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(
                t, {"techdocs-owl-asyncapi": {"spec": "spec.yml"}}, self.ASYNC)
            out = plugin.on_page_markdown("orig", page=page, config=config, files=Files([]))
            self.assertEqual(out, "orig")

    def test_type_is_case_insensitive(self):
        plugin = _plugin()
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(
                t, {"techdocs-owl": {"type": "AsyncAPI", "spec": "spec.yml"}}, self.ASYNC)
            out = plugin.on_page_markdown("orig", page=page, config=config, files=Files([]))
            self.assertIn("# E2E", out)

    def _run(self, meta):
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(t, meta, self.ASYNC)
            return _plugin().on_page_markdown(
                "orig", page=page, config=config, files=Files([]))

    def test_missing_spec_key_is_a_read_error(self):
        """No `spec:` leaves it empty, so the loader tries to read the page directory."""
        out = self._run({"techdocs-owl": {"type": "asyncapi"}})
        self.assertIn('!!! danger "page failed to render"', out)
        self.assertIn("spec read error", out)

    def test_missing_type_is_an_error_page(self):
        """PageOptions.resolve rejects a missing `type:`; on_page_markdown catches it."""
        for meta in ({"spec": "spec.yml"}, {"type": "", "spec": "spec.yml"}):
            with self.subTest(meta=meta):
                out = self._run({"techdocs-owl": meta})
                self.assertIn('!!! danger "page failed to render"', out)
                self.assertIn("missing required `type:` option", out)

    def test_unknown_type_is_an_error_page(self):
        """A typo in `type:` fails the renderer lookup, caught at the boundary."""
        out = self._run({"techdocs-owl": {"type": "openapo", "spec": "spec.yml"}})
        self.assertIn('!!! danger "page failed to render"', out)
        self.assertIn("openapo", out)

    def test_foreign_type_with_spec_is_an_error_page(self):
        """`techdocs-owl:` is shared, but a sibling plugin's type is not skipped."""
        out = self._run({"techdocs-owl": {"type": "javadoc", "spec": "spec.yml"}})
        self.assertIn('!!! danger "page failed to render"', out)
        self.assertIn("javadoc", out)

    def test_foreign_type_without_spec_is_overwritten(self):
        """A sibling's page has no `spec:`, so owl-api replaces its body with an error."""
        out = self._run({"techdocs-owl": {"type": "javadoc", "artifact": "a:b:1"}})
        self.assertIn('!!! danger "page failed to render"', out)
        self.assertIn("spec read error", out)

    def test_bare_string_form_is_an_error_page(self):
        """The short form is gone; a bare string cannot be merged into the options dict."""
        out = self._run({"techdocs-owl": "spec.yml"})
        self.assertIn('!!! danger "page failed to render"', out)
        self.assertIn("TypeError", out)

    def test_failure_is_logged_as_warning(self):
        """`mkdocs build --strict` counts WARNING records, so it must still fail."""
        with self.assertLogs("mkdocs.plugins.mkdocs_owl_api", level="WARNING") as captured:
            self._run({"techdocs-owl": {"type": "openapo", "spec": "spec.yml"}})
        self.assertIn("failed to render", captured.output[0])

    def test_config_defaults(self):
        plugin = _plugin()
        plugin.config = OwlApiConfig()
        plugin.config.load_dict({"hide_version": True})
        plugin.config.validate()
        with tempfile.TemporaryDirectory() as t:
            root, page, config = self._setup(
                t, {"techdocs-owl": {"type": "asyncapi", "spec": "spec.yml"}}, self.ASYNC)
            out = plugin.on_page_markdown("orig", page=page, config=config, files=Files([]))
            self.assertNotIn("**Version:**", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
