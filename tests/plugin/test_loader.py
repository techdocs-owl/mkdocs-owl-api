from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from mkdocs_owl_api.loader import FileReader, SpecError, SpecReader


def _read_spec(ref: str, base: pathlib.Path) -> dict:
    """What `plugin._render` does."""
    return SpecReader(base).read(ref)


class TestFileReaderUri(unittest.TestCase):
    def test_relative_path_resolves_against_base(self):
        reader = FileReader(pathlib.Path("/docs/api"))
        self.assertEqual(reader.uri("s.yml"), "file:///docs/api/s.yml")

    def test_url_passes_through(self):
        reader = FileReader(pathlib.Path("/docs"))
        for url in ("https://ex.com/a.json", "http://ex.com/a.json"):
            self.assertEqual(reader.uri(url), url)

    def test_is_idempotent(self):
        """`SpecReader` re-enters the reader with URIs it already resolved."""
        reader = FileReader(pathlib.Path("/docs"))
        for location in ("s.yml", "https://ex.com/a.json"):
            once = reader.uri(location)
            self.assertEqual(reader.uri(once), once)


class TestSpecReader(unittest.TestCase):
    def _write(self, d: pathlib.Path, name: str, content: str) -> pathlib.Path:
        p = d / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_valid_yaml(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "s.yml", "asyncapi: '3.0.0'\ninfo:\n  title: X\n  version: '1'\n")
            self.assertEqual(_read_spec("s.yml", d)["info"]["title"], "X")

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "s.json", json.dumps({"openapi": "3.0.3", "info": {"title": "J"}}))
            self.assertEqual(_read_spec("s.json", d)["info"]["title"], "J")

    def test_not_found(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SpecError) as ctx:
                _read_spec("missing.yml", pathlib.Path(t))
            self.assertIn("spec file not found", str(ctx.exception))

    def test_empty(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "e.yml", "")
            with self.assertRaises(SpecError) as ctx:
                _read_spec("e.yml", d)
            self.assertIn("spec file is empty", str(ctx.exception))

    def test_not_a_mapping(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "list.yml", "- a\n- b\n")
            with self.assertRaises(SpecError) as ctx:
                _read_spec("list.yml", d)
            self.assertIn("unexpected spec content", str(ctx.exception))

    def test_parse_error(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            self._write(d, "bad.yml", "a: b:\n  - : :\n::::\n")
            with self.assertRaises(SpecError) as ctx:
                _read_spec("bad.yml", d)
            self.assertIn("spec parse error", str(ctx.exception))


class TestExternalRefs(unittest.TestCase):
    def _spec(self, d: pathlib.Path, body: str) -> dict:
        (d / "main.yml").write_text(body, encoding="utf-8")
        return _read_spec("main.yml", d)

    def test_whole_document_ref(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            (d / "child.yml").write_text(
                "type: object\nproperties:\n  x:\n    type: string\n", encoding="utf-8")
            spec = self._spec(d, "payload:\n  $ref: child.yml\n")
            self.assertNotIn("$ref", spec["payload"])
            self.assertEqual(spec["payload"]["type"], "object")
            self.assertIn("x", spec["payload"]["properties"])

    def test_ref_with_json_pointer_fragment(self):
        """`file.yaml#/components/schemas/Error` - the common form."""
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            (d / "common.yml").write_text(
                "components:\n  schemas:\n    Error:\n      type: object\n", encoding="utf-8")
            spec = self._spec(d, "payload:\n  $ref: common.yml#/components/schemas/Error\n")
            self.assertNotIn("$ref", spec["payload"])
            self.assertEqual(spec["payload"]["type"], "object")

    def test_ref_relative_to_referring_document(self):
        """A ref inside a child resolves against the child, not the root spec."""
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            (d / "sub").mkdir()
            (d / "sub" / "child.yml").write_text(
                "payload:\n  $ref: leaf.yml\n", encoding="utf-8")
            (d / "sub" / "leaf.yml").write_text("type: string\n", encoding="utf-8")
            spec = self._spec(d, "a:\n  $ref: sub/child.yml\n")
            self.assertEqual(spec["a"]["payload"]["type"], "string")

    def test_sibling_keys_override_the_target(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            (d / "child.yml").write_text(
                "type: object\ndescription: from target\n", encoding="utf-8")
            spec = self._spec(d, "a:\n  $ref: child.yml\n  description: from sibling\n")
            self.assertEqual(spec["a"]["description"], "from sibling")
            self.assertEqual(spec["a"]["type"], "object")

    def test_cyclic_refs_terminate(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            (d / "a.yml").write_text("child:\n  $ref: b.yml\n", encoding="utf-8")
            (d / "b.yml").write_text("parent:\n  $ref: a.yml\n", encoding="utf-8")
            spec = self._spec(d, "root:\n  $ref: a.yml\n")
            # The cycle is cut where it closes; the `$ref` is left in place there.
            self.assertEqual(spec["root"]["child"]["parent"], {"$ref": "a.yml"})

    def test_shared_ref_targets_are_not_aliased(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            (d / "child.yml").write_text("type: object\n", encoding="utf-8")
            spec = self._spec(d, "a:\n  $ref: child.yml\nb:\n  $ref: child.yml\n")
            self.assertEqual(spec["a"], spec["b"])
            self.assertIsNot(spec["a"], spec["b"])

    def test_unreadable_ref_is_left_alone(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            spec = self._spec(d, "a:\n  $ref: missing.yml\n")
            self.assertEqual(spec["a"], {"$ref": "missing.yml"})

    def test_internal_refs_untouched(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            spec = self._spec(d, "a:\n  $ref: '#/components/schemas/Foo'\n")
            self.assertEqual(spec["a"]["$ref"], "#/components/schemas/Foo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
