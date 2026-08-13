"""
Page rendering shared by every flavour.

`MarkdownRenderer` owns the preamble - what a page says about the API before it
says anything about what the API does - and the joining policy. A flavour
supplies `sections()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..options import PageOptions, ResolvedAttachment
from .doc_model import ApiDoc
from .doc_render import (
    attachment_rows,
    attachments_table,
    contact_line,
    description_block,
    external_docs_line,
    license_line,
    title,
    version_line,
)


@dataclass(frozen=True)
class RenderContext:
    """
    Everything a page needs beyond the description itself, resolved before
    rendering starts.
    """

    options: PageOptions
    spec_url: str = ""
    attachments: tuple[ResolvedAttachment, ...] = ()


def join_blocks(blocks: Iterable[str]) -> str:
    """
    Join rendered blocks into page markdown.

    The container owns separator policy: a block is a complete chunk of
    markdown carrying no leading or trailing blank lines, and blocks are
    separated by exactly one blank line. Blank blocks drop out, which is what
    lets a renderer return `[]` to omit its section entirely without the caller
    testing for it.
    """
    kept = [block.strip("\n") for block in blocks]
    return "\n\n".join(block for block in kept if block.strip())


class MarkdownRenderer:
    """Turns a parsed document into page markdown."""

    def __init__(self, doc: ApiDoc, ctx: RenderContext):
        self.doc = doc
        self.ctx = ctx
        self.options = ctx.options

    def preamble(self) -> list[str]:
        """Blocks every flavour shows, in the order every flavour shows them."""
        info = self.doc.info
        blocks = [f"# {title(info, self.options.title)}"]
        if self.options.intro:
            blocks.append(self.options.intro)
        if not self.options.hide_version:
            blocks.extend(version_line(info))
        blocks.extend(self.specification_line())
        blocks.extend(attachments_table(attachment_rows(
            self.ctx.spec_url, self.options.spec_label,
            self.options.hide_download_link, self.ctx.attachments,
        )))
        blocks.extend(license_line(info))
        blocks.extend(contact_line(info))
        blocks.extend(external_docs_line(self.doc.external_docs))
        blocks.extend(description_block(info))
        return blocks

    def specification_line(self) -> list[str]:
        """Which specification the description was written against."""
        if not self.doc.spec_version:
            return []
        return [
            ":material-file-code: **Specification:** "
            f"`{self.doc.spec_version_key} {self.doc.spec_version}`"
        ]

    def sections(self) -> list[str]:
        """The flavour's own sections. Subclass responsibility."""
        raise NotImplementedError

    def render(self) -> str:
        return join_blocks(self.preamble() + self.sections())
