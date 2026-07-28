"""
The `owl-api` mkdocs plugin.

Renders OpenApi/AsyncApi specification in md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mkdocs.config import config_options as c
from mkdocs.config.base import Config
from mkdocs.plugins import BasePlugin, get_plugin_logger
from mkdocs.structure.files import File

from .loader import _load_spec, _save_attachments, _save_spec
from .render.asyncapi import _render_page as _render_asyncapi_page
from .render.common import _error_page
from .render.openapi import _render_openapi_page

log = get_plugin_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_CSS_FILENAME = "techdocs-owl-api.css"
_CSS_SRC_URI = f"assets/{_CSS_FILENAME}"

_ASYNCAPI_KEY = "techdocs-owl-asyncapi"
_OPENAPI_KEY = "techdocs-owl-openapi"


class OwlApiConfig(Config):
    schema_depth = c.Type(int, default=3)
    hide_internal = c.Type(bool, default=False)
    hide_bindings = c.Type(bool, default=False)
    hide_traits = c.Type(bool, default=False)
    hide_security = c.Type(bool, default=False)
    hide_version = c.Type(bool, default=False)
    hide_download_link = c.Type(bool, default=False)


def _normalize_frontmatter(raw: Any) -> dict[str, Any] | None:
    """
    Accept the short form (a bare spec path/URL string) or a mapping with a `spec` key. Returns a dict or None if unparseable.
    """
    if isinstance(raw, str):
        return {"spec": raw}
    if isinstance(raw, dict) and isinstance(raw.get("spec"), str):
        return dict(raw)
    return None


class OwlApiPlugin(BasePlugin[OwlApiConfig]):
    def on_config(self, config, **kwargs):
        config.extra_css.append(_CSS_SRC_URI)
        return config

    def on_files(self, files, *, config, **kwargs):
        css_path = _STATIC_DIR / _CSS_FILENAME
        files.append(File.generated(
            config, _CSS_SRC_URI, content=css_path.read_text(encoding="utf-8"),
        ))
        return files

    def on_page_markdown(self, markdown, *, page, config, files, **kwargs):
        defaults = dict(self.config)

        raw = (page.meta or {}).get(_ASYNCAPI_KEY)
        if raw is not None:
            return self._render(raw, page, config, files, defaults, kind="asyncapi", key=_ASYNCAPI_KEY)

        raw = (page.meta or {}).get(_OPENAPI_KEY)
        if raw is not None:
            return self._render(raw, page, config, files, defaults, kind="openapi", key=_OPENAPI_KEY)

        return markdown

    def _render(self, raw, page, config, files, defaults, *, kind: str, key: str) -> str:
        page_opts = _normalize_frontmatter(raw)
        if page_opts is None:
            return _error_page(
                "invalid frontmatter",
                f"`{key}:` must be a path string or a mapping with a `spec:` key.",
            )
        opts = {**defaults, **page_opts}
        base = Path(page.file.abs_src_path).resolve().parent
        log.info("found %s spec in page '%s' with url '%s'", kind, page.file.src_path, opts["spec"])
        spec, error = _load_spec(opts["spec"], base)
        if error:
            return error
        download_link = _save_spec(spec, page, config, files)
        attachments = _save_attachments(opts, page, config, files)
        renderer = _render_asyncapi_page if kind == "asyncapi" else _render_openapi_page
        return renderer(spec, opts, spec_url=download_link, attachments=attachments)
