"""
Document metadata in, page blocks out.

Everything here reads the flavour-neutral part of a description - `info` and its
neighbours - plus the page-level extras the plugin resolved before rendering.
"""

from __future__ import annotations

from .doc_model import ExternalDocs, Info
from .primitives import _demote_headings, _file_format, _table_cell

ATTACHMENT_HEADERS = ("Attachment", "Description")


def title(info: Info, override: str = "") -> str:
    return (override or info.title or "API Reference").strip()


def version_line(info: Info) -> list[str]:
    version = (info.version or "").strip()
    return [f"**Version:** `{version}`"] if version else []


def license_line(info: Info) -> list[str]:
    if info.license is None:
        return []
    name = info.license.name or info.license.identifier or "license"
    target = f"[{name}]({info.license.url})" if info.license.url else name
    return [f":material-scale-balance: **License:** {target}"]


def contact_line(info: Info) -> list[str]:
    if info.contact is None:
        return []
    contact = info.contact
    bits: list[str] = []
    if contact.name:
        bits.append(contact.name)
    if contact.email:
        bits.append(f"[{contact.email}](mailto:{contact.email})")
    if contact.url:
        bits.append(f"[{contact.url}]({contact.url})")
    return [f":material-contacts: **Contact:** {', '.join(bits)}"] if bits else []


def external_docs_line(docs: ExternalDocs | None) -> list[str]:
    if docs is None or not docs.url:
        return []
    label = docs.description or docs.url
    return [f":material-link-variant: **External documentation:** [{label}]({docs.url})"]


def description_block(info: Info) -> list[str]:
    """`info.description`, demoted so its headings nest under the page title."""
    description = (info.description or "").strip()
    return [_demote_headings(description)] if description else []


def attachments_table(rows: list[tuple[str, str]]) -> list[str]:
    """
    The downloads table.

    A pipe table, not HTML: every cell is a single line, and the cells are
    flattened so a user-supplied title cannot break out of one.
    """
    if not rows:
        return []
    out = ["| " + " | ".join(ATTACHMENT_HEADERS) + " |", "|---|---|"]
    out += [f"| {label} | {description} |" for label, description in rows]
    return ["\n".join(out)]


def attachment_rows(spec_url: str, spec_label: str, hide_download_link: bool,
                    attachments) -> list[tuple[str, str]]:
    """The spec itself, then whatever else the page declared."""
    rows: list[tuple[str, str]] = []

    if spec_url and not hide_download_link:
        rows.append((
            f":material-file-document: [Specification Source]({spec_url})",
            f"{spec_label} specification in {_file_format(spec_url)} format",
        ))

    for attachment in attachments:
        label = _table_cell(attachment.title)
        description = _table_cell(attachment.description)
        if attachment.url:
            rows.append((
                f":material-file-document: [{label}]({attachment.url})", description,
            ))
        else:
            unavailable = f"_(unavailable: {_table_cell(attachment.error)})_"
            rows.append((f":material-file-document: {label} {unavailable}", description))

    return rows
