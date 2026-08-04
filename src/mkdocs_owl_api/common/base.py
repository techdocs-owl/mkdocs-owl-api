"""
Base types for the builder hierarchy: the shared render context, the block
protocol, and the abstract page/part builders.

`common` never imports `openapi` or `asyncapi` - `PageBuilder` is subclassed by
both flavours, so an import the other way would be a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..options import PageOptions, ResolvedAttachment
from .primitives import _file_format, _table_cell


@dataclass(frozen=True)
class RenderContext:
    """
    Everything a builder needs, resolved once before rendering starts.

    Read-only for the whole render. Anything a builder would otherwise thread
    through 6-7 parameter signatures belongs here; anything a builder computes
    for itself does not - see `.tasks/render-builders.md`, "State discipline".
    """

    spec: dict[str, Any]
    options: PageOptions
    spec_url: str = ""
    attachments: tuple[ResolvedAttachment, ...] = ()

    @property
    def info(self) -> dict[str, Any]:
        got = self.spec.get("info")
        return got if isinstance(got, dict) else {}


def join_blocks(blocks: Iterable[str]) -> str:
    """
    Join rendered blocks into page markdown.

    The container owns separator policy: a block is a complete chunk of
    markdown carrying no leading or trailing blank lines, and blocks are
    separated by exactly one blank line. Blank blocks drop out, which is what
    lets a builder return `[]` to omit its section entirely without the caller
    testing for it.

    Trailing `---` is dropped too: section builders emit it between items, so
    the last one would otherwise dangle at the end of the page.
    """
    kept: list[str] = []
    for block in blocks:
        text = block.strip("\n")
        if text.strip():
            kept.append(text)
    while kept and kept[-1].strip() == "---":
        kept.pop()
    return "\n\n".join(kept)


class BlockBuilder:
    """
    Base class for everything that contributes markdown to a page.
    """

    def __init__(self, ctx: RenderContext):
        self.ctx = ctx

    @property
    def spec(self) -> dict[str, Any]:
        return self.ctx.spec

    @property
    def options(self) -> PageOptions:
        return self.ctx.options

    def build(self) -> list[str]:
        raise NotImplementedError


class AttachmentsBuilder(BlockBuilder):
    """
    The downloads table: the spec itself plus any configured attachments.
    """

    def build(self) -> list[str]:
        rows: list[tuple[str, str]] = []

        if self.ctx.spec_url and not self.options.hide_download_link:
            rows.append((
                f":material-file-document: [Specification Source]({self.ctx.spec_url})",
                f"{self.options.spec_label} specification"
                f" in {_file_format(self.ctx.spec_url)} format",
            ))

        for att in self.ctx.attachments:
            title = _table_cell(att.title)
            description = _table_cell(att.description)
            if att.url:
                rows.append((
                    f":material-file-document: [{title}]({att.url})", description,
                ))
            else:
                unavailable = f"_(unavailable: {_table_cell(att.error)})_"
                rows.append((
                    f":material-file-document: {title} {unavailable}", description,
                ))

        if not rows:
            return []

        out = ["| Attachment | Description |", "|---|---|"]
        out.extend(f"| {label} | {description} |" for label, description in rows)
        return ["\n".join(out)]


class PageBuilder:
    """
    Base class for MkDocs page builders.

    Owns the preamble shared by every flavour - title, intro, version,
    downloads - and the joining policy.
    """

    def __init__(self, ctx: RenderContext):
        self.ctx = ctx

    @property
    def spec(self) -> dict[str, Any]:
        return self.ctx.spec

    @property
    def options(self) -> PageOptions:
        return self.ctx.options

    @property
    def info(self) -> dict[str, Any]:
        return self.ctx.info

    def title(self) -> str:
        return (
            self.options.title or self.info.get("title") or "API Reference"
        ).strip()

    def version(self) -> str:
        return (self.info.get("version") or "").strip()

    def preamble(self) -> list[str]:
        """Blocks every flavour emits, in the order every flavour emits them."""
        blocks = [f"# {self.title()}"]
        if self.options.intro:
            blocks.append(self.options.intro)
        version = self.version()
        if version and not self.options.hide_version:
            blocks.append(f"**Version:** `{version}`")
        blocks.extend(AttachmentsBuilder(self.ctx).build())
        return blocks

    def sections(self) -> list[BlockBuilder]:
        """The flavour's section order. Subclass responsibility."""
        raise NotImplementedError

    def build_page(self) -> str:
        """Render the whole page to markdown."""
        blocks = list(self.preamble())
        for builder in self.sections():
            blocks.extend(builder.build())
        return join_blocks(blocks)
