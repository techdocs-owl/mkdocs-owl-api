"""
Fetch AsyncAPI/OpenAPI specs from local paths or HTTP(S) URLs, resolve external `$ref`s recursively,
persist the resolved spec plus any declared attachments as downloadable build assets.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from mkdocs.structure.files import File

from .options import Attachment, ResolvedAttachment

ASSET_DIR = "assets/techdocs-owl-api"


class SpecError(Exception):
    """The spec could not be fetched, read or parsed."""


def _fetch_and_parse(uri: str, cache: dict[str, Any]) -> Any:
    """
    Fetch a URI (HTTP URL or local file path) and parse as JSON/YAML.
    """
    if uri in cache:
        return cache[uri]

    if uri.startswith("http://") or uri.startswith("https://"):
        try:
            with urllib.request.urlopen(uri, timeout=30) as resp:
                text = resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError):
            cache[uri] = None
            return None
    else:
        try:
            text = Path(uri).read_text(encoding="utf-8")
        except OSError:
            cache[uri] = None
            return None

    try:
        result = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        try:
            result = yaml.safe_load(text)
        except yaml.YAMLError:
            result = None
    cache[uri] = result
    return result


def _resolve_uri(ref: str, base_uri: str) -> str:
    """
    Resolve a $ref against a base URI (URL or file path).
    """
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref
    if base_uri.startswith("http://") or base_uri.startswith("https://"):
        from urllib.parse import urljoin
        return urljoin(base_uri, ref)
    return str((Path(base_uri).parent / ref).resolve())


def _base_uri_for(uri: str) -> str:
    """
    Return the base URI to use for resolving relative refs within a document.
    """
    return uri


def _resolve_external_refs(node: Any, base_uri: str, cache: dict[str, Any] | None = None) -> None:
    """
    Recursively resolve external `$ref` values in-place.
    Internal `#/...` refs are left untouched.
    """
    if cache is None:
        cache = {}
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#"):
            resolved_uri = _resolve_uri(ref, base_uri)
            resolved = _fetch_and_parse(resolved_uri, cache)
            if isinstance(resolved, dict):
                node.pop("$ref")
                node.update(resolved)
                _resolve_external_refs(node, _base_uri_for(resolved_uri), cache)
            return
        for v in node.values():
            _resolve_external_refs(v, base_uri, cache)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)):
                _resolve_external_refs(item, base_uri, cache)


def _load_spec(spec_ref: str, base: Path) -> dict[str, Any]:
    """
    Load and parse (JSON or YAML) an AsyncAPI/OpenAPI spec from a local path or HTTP(S) URL.

    Raises `SpecError` on any failure - `on_page_markdown` turns it into an error page.
    """
    is_url = spec_ref.startswith("http://") or spec_ref.startswith("https://")

    if is_url:
        try:
            with urllib.request.urlopen(spec_ref, timeout=30) as resp:
                text = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise SpecError(f"spec HTTP error: `{spec_ref}`: {exc.code} {exc.reason}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise SpecError(f"spec fetch error: `{spec_ref}`: {exc}") from exc
    else:
        spec_path = (base / spec_ref).resolve()
        try:
            text = spec_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise SpecError(f"spec file not found: `{spec_path}`") from exc
        except OSError as exc:
            raise SpecError(f"spec read error: `{spec_path}`: {exc}") from exc

    source_label = spec_ref if is_url else str(spec_path)

    spec: Any = None
    try:
        spec = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        try:
            spec = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SpecError(f"spec parse error: `{source_label}`: {exc}") from exc

    if spec is None:
        raise SpecError(f"spec file is empty: `{source_label}` contains no content.")
    if not isinstance(spec, dict):
        raise SpecError(f"unexpected spec content: `{source_label}` did not parse to a mapping.")

    _resolve_external_refs(spec, spec_ref if is_url else str(spec_path))

    return spec


def _read_bytes(src: str, base: Path) -> tuple[bytes | None, str | None]:
    """Read raw bytes from a local path or HTTP(S) URL.

    Returns (content, None) on success or (None, error_message) on failure.
    """
    if src.startswith("http://") or src.startswith("https://"):
        try:
            with urllib.request.urlopen(src, timeout=30) as resp:
                return resp.read(), None
        except urllib.error.HTTPError as exc:
            return None, f"{exc.code} {exc.reason}"
        except (urllib.error.URLError, OSError) as exc:
            return None, str(exc)
    path = (base / src).resolve()
    try:
        return path.read_bytes(), None
    except OSError as exc:
        return None, str(exc)


def _register(files, config, rel_path: str, content: str | bytes) -> None:
    """Add `content` to the build as a generated file at {ASSET_DIR}/... .
    """
    existing = files.get_file_from_path(rel_path)
    if existing is not None:
        files.remove(existing)
    files.append(File.generated(config, rel_path, content=content))


def _save_spec(spec: dict[str, Any], page, config, files) -> str:
    """Register the resolved spec as {ASSET_DIR}/<slug>.json
    and return the relative URL to the spec file from the page.
    """
    slug = Path(page.file.src_path).stem
    rel_spec = f"{ASSET_DIR}/{slug}.json"
    _register(files, config, rel_spec, json.dumps(spec, indent=2, default=str))

    page_dir = Path(page.file.src_path).parent
    up = "../" * len(page_dir.parts)
    return f"{up}{rel_spec}"


def _save_attachments(
    attachments: Sequence[Attachment], page, config, files,
) -> list[ResolvedAttachment]:
    """Read each attachment, register it as {ASSET_DIR}/<slug>-<filename>,
    and return one `ResolvedAttachment` each (url is None on failure).

    Entries arrive already parsed as `Attachment`s, so shape handling lives in
    `options`, not here.
    """
    if not attachments:
        return []

    base = Path(page.file.abs_src_path).resolve().parent
    slug = Path(page.file.src_path).stem
    page_dir = Path(page.file.src_path).parent
    up = "../" * len(page_dir.parts)

    results: list[ResolvedAttachment] = []
    for item in attachments:
        src = item.path
        is_url = src.startswith("http://") or src.startswith("https://")
        filename = src.split("?")[0].rsplit("/", 1)[-1] if is_url else Path(src).name
        label = item.title or filename

        content, err = _read_bytes(src, base)
        if err is not None:
            results.append(ResolvedAttachment(
                title=label, description=item.description, error=err))
            continue

        out_name = f"{slug}-{filename}"
        rel_path = f"{ASSET_DIR}/{out_name}"
        _register(files, config, rel_path, content)

        results.append(ResolvedAttachment(
            title=label, description=item.description, url=f"{up}{rel_path}"))

    return results
