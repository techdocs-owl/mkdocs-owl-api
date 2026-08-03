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


class PartBuilder:
    """
    Base class for page part builders.

    Subclasses return *blocks*, never lines with hand-managed `""` separators.
    An empty list means the part contributes nothing.
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


class PageBuilder:
    """
    Base class for MkDocs page builders.

    Owns the preamble shared by every flavour - title, intro, version,
    downloads - and the joining policy. The section order after the preamble is
    the subclass's, which is why there is no externally-driven configuration
    phase and so no window in which a half-configured builder is observable.
    """

    #: Label used for the spec row of the downloads table ("OpenAPI"/"AsyncAPI").
    spec_type: str = ""

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
        return blocks

    def sections(self) -> list[PartBuilder]:
        """The flavour's section order. Subclass responsibility."""
        raise NotImplementedError

    def build_page(self) -> str:
        """Render the whole page to markdown."""
        blocks = list(self.preamble())
        for builder in self.sections():
            blocks.extend(builder.build())
        return join_blocks(blocks)
