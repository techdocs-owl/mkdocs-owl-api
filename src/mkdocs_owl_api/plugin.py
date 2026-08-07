"""
The `owl-api` mkdocs plugin.

Renders OpenApi/AsyncApi specification in md.
"""

from __future__ import annotations

from pathlib import Path

from mkdocs.config import config_options as mkdocs_config_options
from mkdocs.config.base import Config
from mkdocs.plugins import BasePlugin, get_plugin_logger
from mkdocs.structure.files import File

from .asyncapi.render import AsyncApiPageBuilder
from .common.render import PageBuilder, RenderContext
from .loader import _load_spec, _save_attachments, _save_spec
from .openapi.render import OpenApiPageBuilder
from .options import PageOptions, site_default

log = get_plugin_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_CSS_FILENAME = "techdocs-owl-api.css"
_CSS_SRC_URI = f"assets/{_CSS_FILENAME}"

_FRONTMATTER_KEY = "techdocs-owl"

#: `type:` -> page builder. The dispatch seam a sibling `techdocs-owl-*` plugin
#: relies on: a `type:` this plugin does not own must pass through untouched.
_RENDERERS: dict[str, type[PageBuilder]] = {
    "openapi": OpenApiPageBuilder,
    "asyncapi": AsyncApiPageBuilder,
}


def _error_page(title: str, detail: str) -> str:
    """
    Body shown in place of a reference when a page cannot be rendered.

    The single place a failure becomes page content - everything below
    `on_page_markdown` raises instead.
    """
    return (
        "# API reference failed to render\n\n"
        f'!!! danger "{title}"\n'
        f"    {detail}\n"
    )


class OwlApiConfig(Config):
    schema_depth = mkdocs_config_options.Type(int, default=site_default("schema_depth"))
    hide_internal = mkdocs_config_options.Type(bool, default=site_default("hide_internal"))
    hide_bindings = mkdocs_config_options.Type(bool, default=site_default("hide_bindings"))
    hide_traits = mkdocs_config_options.Type(bool, default=site_default("hide_traits"))
    hide_security = mkdocs_config_options.Type(bool, default=site_default("hide_security"))
    hide_version = mkdocs_config_options.Type(bool, default=site_default("hide_version"))
    hide_download_link = mkdocs_config_options.Type(
        bool, default=site_default("hide_download_link"))

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
        raw = (page.meta or {}).get(_FRONTMATTER_KEY)
        if raw is None:
            return markdown

        try:
            page_options = PageOptions.resolve(dict(self.config), raw)
            return self._render(page_options, page, config, files)
        except Exception as exc:
            # Keep one bad page from aborting the whole site. Logged at warning
            # level so `mkdocs build --strict` still fails on it.
            log.warning("failed to render '%s': %s", page.file.src_path, exc, exc_info=True)
            return _error_page(
                "page failed to render",
                f"`{page.file.src_path}`: {type(exc).__name__}: {exc}",
            )

    def _render(self, opts: PageOptions, page, config, files) -> str:
        base = Path(page.file.abs_src_path).resolve().parent
        log.info("found %s spec in page '%s' with url '%s'",
                 opts.type, page.file.src_path, opts.spec)
        spec = _load_spec(opts.spec, base)

        # Assets are registered here, before rendering, so that the builders
        # receive resolved data and never touch mkdocs objects. mkdocs calls
        # `page.render(config, files)` straight after `on_page_markdown`, so
        # registration has to be complete by the time we return - see CLAUDE.md.
        download_link = _save_spec(spec, page, config, files)
        attachments = _save_attachments(opts.attachments, page, config, files)

        return _RENDERERS[opts.type](RenderContext(
            spec=spec,
            options=opts,
            spec_url=download_link,
            attachments=tuple(attachments),
        )).build_page()
