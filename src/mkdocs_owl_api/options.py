from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

DEFAULT_SCHEMA_DEPTH = 3
MIN_SCHEMA_DEPTH = 1

_TRUTHY = frozenset({"true", "yes", "on", "1"})
_FALSY = frozenset({"false", "no", "off", "0", ""})

#: `type:` -> how that flavour is spelled in prose. Keyed like `_RENDERERS` in
#: `plugin.py`; a `type:` this plugin does not own never reaches a renderer, so
#: the fallback is a guard rather than a supported path.
_SPEC_LABELS = {
    "openapi": "OpenAPI",
    "asyncapi": "AsyncAPI",
    "jsonschema": "JSON Schema",
}


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUTHY:
            return True
        if text in _FALSY:
            return False
    return default


def _as_int(value: Any, default: int, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or value is None:
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        result = max(minimum, result)
    return result


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_attachments(value: Any) -> tuple[Attachment, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    parsed: list[Attachment] = []
    for entry in value:
        if isinstance(entry, str):
            parsed.append(Attachment(path=_as_str(entry)))
        elif isinstance(entry, dict) and isinstance(entry.get("path"), str):
            parsed.append(Attachment(
                path=_as_str(entry["path"]),
                title=_as_str(entry.get("title")),
                description=_as_str(entry.get("description")),
            ))
    return tuple(parsed)


@dataclass(frozen=True)
class Attachment:
    """An attachment as configured on the page, before it has been read."""

    path: str
    title: str = ""
    description: str = ""


@dataclass(frozen=True)
class ResolvedAttachment:
    """
    An attachment after the loader has read and registered it.

    `url` is None exactly when `error` is set. Declared once here so the
    renderers and the loader cannot drift on the shape.
    """

    title: str
    description: str = ""
    url: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class PageOptions:
    type: str = ""
    spec: str = ""
    title: str = ""
    intro: str = ""
    schema_depth: int = DEFAULT_SCHEMA_DEPTH
    hide_internal: bool = False
    hide_version: bool = False
    hide_download_link: bool = False
    hide_bindings: bool = False
    hide_security: bool = False
    attachments: tuple[Attachment, ...] = ()

    @property
    def spec_label(self) -> str:
        """
        Display form of `type:`, for prose and table cells.

        `type` is the single source of the flavour - the one the user wrote and
        the one dispatch keys on - so nothing downstream has to declare its own
        name for itself.
        """
        return _SPEC_LABELS.get(self.type, self.type)

    @classmethod
    def resolve(
        cls,
        defaults: dict[str, Any] | None = None,
        page_opts: dict[str, Any] | None = None,
    ) -> PageOptions:
        merged: dict[str, Any] = {**(defaults or {}), **(page_opts or {})}
        kind = _as_str(merged.get("type")).lower()
        if not kind:
            raise ValueError("missing required `type:` option")
        return cls(
            type=kind,
            spec=_as_str(merged.get("spec")),
            title=_as_str(merged.get("title")),
            intro=_as_str(merged.get("intro")),
            schema_depth=_as_int(
                merged.get("schema_depth"),
                DEFAULT_SCHEMA_DEPTH,
                minimum=MIN_SCHEMA_DEPTH,
            ),
            hide_internal=_as_bool(merged.get("hide_internal")),
            hide_version=_as_bool(merged.get("hide_version")),
            hide_download_link=_as_bool(merged.get("hide_download_link")),
            hide_bindings=_as_bool(merged.get("hide_bindings")),
            hide_security=_as_bool(merged.get("hide_security")),
            attachments=_as_attachments(merged.get("attachments")),
        )


def site_default(name: str) -> Any:
    """
    Default for a site-wide option, read off the dataclass field definitions so
    `OwlApiConfig` cannot drift from what the renderers actually fall back to.
    """
    for field_ in fields(PageOptions):
        if field_.name == name:
            return field_.default
    raise KeyError(name)
