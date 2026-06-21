"""
Fetch AsyncAPI/OpenAPI specs from local paths or HTTP(S) URLs, resolve external `$ref`s recursively,
persist the resolved spec plus any declared attachments as downloadable build assets.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from .render.common import _error_page

ASSET_DIR = "assets/techdocs-owl-api"


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


def _load_spec(spec_ref: str, base: Path) -> tuple[dict[str, Any] | None, str | None]:
    """
    Load and parse (JSON or YAML) an AsyncAPI/OpenAPI spec from a local path or HTTP(S) URL.
    Returns (spec_dict, None) on success or (None, error_page_markdown) on failure.
    """
    is_url = spec_ref.startswith("http://") or spec_ref.startswith("https://")

    if is_url:
        try:
            with urllib.request.urlopen(spec_ref, timeout=30) as resp:
                text = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return None, _error_page("spec HTTP error", f"`{spec_ref}`: {exc.code} {exc.reason}")
        except (urllib.error.URLError, OSError) as exc:
            return None, _error_page("spec fetch error", f"`{spec_ref}`: {exc}")
    else:
        spec_path = (base / spec_ref).resolve()
        try:
            text = spec_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None, _error_page("spec file not found", f"`{spec_path}`")
        except OSError as exc:
            return None, _error_page("spec read error", f"`{spec_path}`: {exc}")

    source_label = spec_ref if is_url else str(spec_path)

    spec: Any = None
    try:
        spec = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        try:
            spec = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            return None, _error_page("spec parse error", f"`{source_label}`: {exc}")

    if spec is None:
        return None, _error_page("spec file is empty", f"`{source_label}` contains no content.")
    if not isinstance(spec, dict):
        return None, _error_page("unexpected spec content", f"`{source_label}` did not parse to a mapping.")

    _resolve_external_refs(spec, spec_ref if is_url else str(spec_path))

    return spec, None


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


def _save_spec(spec: dict[str, Any], page, config) -> str:
    """Write the resolved spec to both docs/ and site/ {ASSET_DIR}/<slug>.json
    and return the relative URL to the spec file from the page.
    """
    slug = Path(page.file.src_path).stem
    rel_spec = f"{ASSET_DIR}/{slug}.json"
    content = json.dumps(spec, indent=2, default=str)

    docs_out = Path(config["docs_dir"]) / rel_spec
    docs_out.parent.mkdir(parents=True, exist_ok=True)
    docs_out.write_text(content, encoding="utf-8")

    site_out = Path(config["site_dir"]) / rel_spec
    site_out.parent.mkdir(parents=True, exist_ok=True)
    site_out.write_text(content, encoding="utf-8")

    page_dir = Path(page.file.src_path).parent
    up = "../" * len(page_dir.parts)
    return f"{up}{rel_spec}"


def _save_attachments(opts: dict[str, Any], page, config) -> list[dict[str, Any]]:
    """Read each attachment, copy it to {ASSET_DIR}/<slug>-<filename>,
    and return a list of {title, url, error} dicts (url is None on failure).
    """
    raw = opts.get("attachments")
    if not isinstance(raw, list) or not raw:
        return []

    base = Path(page.file.abs_src_path).resolve().parent
    slug = Path(page.file.src_path).stem
    page_dir = Path(page.file.src_path).parent
    up = "../" * len(page_dir.parts)

    results: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            src, title = item, None
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            src, title = item["path"], item.get("title")
        else:
            continue

        is_url = src.startswith("http://") or src.startswith("https://")
        filename = src.split("?")[0].rsplit("/", 1)[-1] if is_url else Path(src).name
        label = title or filename

        content, err = _read_bytes(src, base)
        if err is not None:
            results.append({"title": label, "url": None, "error": err})
            continue

        out_name = f"{slug}-{filename}"
        rel_path = f"{ASSET_DIR}/{out_name}"
        for root_key in ("docs_dir", "site_dir"):
            out = Path(config[root_key]) / rel_path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(content)

        results.append({"title": label, "url": f"{up}{rel_path}", "error": None})

    return results
