"""
Publish the resolved spec and a page's declared attachments as build assets.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from mkdocs.structure.files import File
from mkdocs.utils import get_relative_url

from .loader import FileReader
from .options import Attachment, ResolvedAttachment

ASSET_DIR = "assets/techdocs-owl-api"


def _filename(uri: str) -> str:
    """The last path segment of a URI, with any query string and escaping removed."""
    return unquote(PurePosixPath(urlsplit(uri).path).name)


def _register(files, config, rel_path: str, content: str | bytes) -> None:
    """
    Add `content` to the build as a generated file at {ASSET_DIR}/... .
    """
    existing = files.get_file_from_path(rel_path)
    if existing is not None:
        files.remove(existing)
    files.append(File.generated(config, rel_path, content=content))


def _save_spec(spec: dict[str, Any], page, config, files) -> str:
    """
    Register the resolved spec as {ASSET_DIR}/<slug>.json
    and return the relative URL to the spec file from the page.
    """
    rel_path = f"{ASSET_DIR}/{Path(page.file.src_path).stem}.json"
    _register(files, config, rel_path, json.dumps(spec, indent=2, default=str))
    return get_relative_url(rel_path, page.file.src_uri)


def _save_attachments(
    attachments: Sequence[Attachment], page, config, files,
) -> list[ResolvedAttachment]:
    """
    Read each attachment, register it as {ASSET_DIR}/<slug>-<filename>,
    and return one `ResolvedAttachment` each (url is None on failure).

    Entries arrive already parsed as `Attachment`s, so shape handling lives in
    `options`, not here.
    """
    if not attachments:
        return []

    slug = Path(page.file.src_path).stem
    reader = FileReader(Path(page.file.abs_src_path).resolve().parent)

    results: list[ResolvedAttachment] = []
    for item in attachments:
        uri = reader.uri(item.path)
        filename = _filename(uri)
        label = item.title or filename

        try:
            content = reader.read_bytes(uri)
        except Exception as exc:
            results.append(ResolvedAttachment(
                title=label, description=item.description, error=str(exc)))
            continue

        rel_path = f"{ASSET_DIR}/{slug}-{filename}"
        _register(files, config, rel_path, content)

        results.append(ResolvedAttachment(
            title=label, description=item.description,
            url=get_relative_url(rel_path, page.file.src_uri)))

    return results
