from __future__ import annotations

import unittest

from mkdocs_owl_api.common.base import (
    PageBuilder,
    BlockBuilder,
    RenderContext,
    join_blocks,
)
from mkdocs_owl_api.options import PageOptions


def _ctx(spec=None, **opts) -> RenderContext:
    return RenderContext(
        spec=spec if spec is not None else {},
        options=PageOptions(type="openapi", **opts),
    )


class TestJoinBlocks(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(join_blocks([]), "")

    def test_single_block_has_no_trailing_newline(self):
        self.assertEqual(join_blocks(["# Title"]), "# Title")

    def test_blocks_separated_by_one_blank_line(self):
        self.assertEqual(join_blocks(["a", "b", "c"]), "a\n\nb\n\nc")

    def test_blank_blocks_drop_out(self):
        # A builder returning [] or [""] omits its section without the caller
        # testing for it.
        self.assertEqual(join_blocks(["a", "", "b"]), "a\n\nb")
        self.assertEqual(join_blocks(["a", "   ", "\n\n", "b"]), "a\n\nb")

    def test_block_own_blank_lines_are_stripped(self):
        self.assertEqual(join_blocks(["\na\n\n", "\n\nb\n"]), "a\n\nb")

    def test_internal_blank_lines_survive(self):
        self.assertEqual(join_blocks(["a\n\nstill a", "b"]), "a\n\nstill a\n\nb")

    def test_trailing_rule_is_dropped(self):
        self.assertEqual(join_blocks(["a", "---"]), "a")
        self.assertEqual(join_blocks(["a", "---", "", "---"]), "a")

    def test_internal_rule_survives(self):
        self.assertEqual(join_blocks(["a", "---", "b"]), "a\n\n---\n\nb")


class _Static(BlockBuilder):
    def __init__(self, ctx, blocks):
        super().__init__(ctx)
        self._blocks = blocks

    def build(self):
        return self._blocks


class TestBlockBuilder(unittest.TestCase):
    def test_build_is_abstract(self):
        with self.assertRaises(NotImplementedError):
            BlockBuilder(_ctx()).build()

    def test_exposes_context(self):
        ctx = _ctx(spec={"info": {"title": "T"}}, hide_internal=True)
        part = _Static(ctx, [])
        self.assertIs(part.spec, ctx.spec)
        self.assertTrue(part.options.hide_internal)


class TestPageBuilder(unittest.TestCase):
    def test_sections_is_abstract(self):
        with self.assertRaises(NotImplementedError):
            PageBuilder(_ctx()).build_page()

    def test_title_prefers_option_over_spec(self):
        ctx = _ctx(spec={"info": {"title": "From spec"}}, title="From option")
        self.assertEqual(PageBuilder(ctx).title(), "From option")

    def test_title_falls_back_to_spec_then_default(self):
        self.assertEqual(
            PageBuilder(_ctx(spec={"info": {"title": " From spec "}})).title(),
            "From spec",
        )
        self.assertEqual(PageBuilder(_ctx()).title(), "API Reference")

    def test_preamble_order_and_omissions(self):
        ctx = _ctx(spec={"info": {"title": "T", "version": "1.2.3"}}, intro="Hi.")
        self.assertEqual(
            PageBuilder(ctx).preamble(),
            ["# T", "Hi.", "**Version:** `1.2.3`"],
        )

    def test_preamble_without_intro_or_version(self):
        self.assertEqual(PageBuilder(_ctx(spec={"info": {"title": "T"}})).preamble(), ["# T"])

    def test_hide_version_suppresses_version(self):
        ctx = _ctx(spec={"info": {"title": "T", "version": "1.0"}}, hide_version=True)
        self.assertEqual(PageBuilder(ctx).preamble(), ["# T"])

    def test_build_page_appends_sections_in_order(self):
        ctx = _ctx(spec={"info": {"title": "T"}})

        class Page(PageBuilder):
            def sections(self):
                return [_Static(ctx, ["## A", "body a"]), _Static(ctx, []), _Static(ctx, ["## B"])]

        self.assertEqual(Page(ctx).build_page(), "# T\n\n## A\n\nbody a\n\n## B")

    def test_info_tolerates_missing_or_malformed(self):
        self.assertEqual(RenderContext(spec={}, options=PageOptions(type="openapi")).info, {})
        self.assertEqual(
            RenderContext(spec={"info": "nope"}, options=PageOptions(type="openapi")).info, {}
        )


if __name__ == "__main__":
    unittest.main()
