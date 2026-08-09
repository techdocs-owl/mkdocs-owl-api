from __future__ import annotations

import html as _html
from enum import Enum
from typing import Any, Iterable


class Color(str, Enum):
    BLUE = "blue"
    GREEN = "green"
    TEAL = "teal"
    RED = "red"
    ORANGE = "orange"
    AMBER = "amber"
    PURPLE = "purple"
    INDIGO = "indigo"
    GREY = "grey"


def pill(
    label: str,
    *,
    color: Color | str = Color.GREY,
    title: str | None = None,
    strike: bool = False,
) -> str:
    classes = [
        "techdocs-owl-api-pill",
        f"techdocs-owl-api-pill--{getattr(color, 'value', color)}",
    ]
    if strike:
        classes.append("techdocs-owl-api-pill--strike")
    title_attr = f' title="{_html.escape(title)}"' if title else ""
    return (
        f'<span class="{" ".join(classes)}"{title_attr}>'
        f'{_html.escape(label)}'
        f'</span>'
    )


def pill_blue(label: str, *, title: str | None = None, strike: bool = False) -> str:
    return pill(label, color=Color.BLUE, title=title, strike=strike)


def pill_green(label: str, *, title: str | None = None, strike: bool = False) -> str:
    return pill(label, color=Color.GREEN, title=title, strike=strike)


def pill_teal(label: str, *, title: str | None = None, strike: bool = False) -> str:
    return pill(label, color=Color.TEAL, title=title, strike=strike)


def pill_red(label: str, *, title: str | None = None, strike: bool = False) -> str:
    return pill(label, color=Color.RED, title=title, strike=strike)


def pill_orange(label: str, *, title: str | None = None, strike: bool = False) -> str:
    return pill(label, color=Color.ORANGE, title=title, strike=strike)


def pill_amber(label: str, *, title: str | None = None, strike: bool = False) -> str:
    return pill(label, color=Color.AMBER, title=title, strike=strike)


def pill_purple(label: str, *, title: str | None = None, strike: bool = False) -> str:
    return pill(label, color=Color.PURPLE, title=title, strike=strike)


def pill_indigo(label: str, *, title: str | None = None, strike: bool = False) -> str:
    return pill(label, color=Color.INDIGO, title=title, strike=strike)


def pill_grey(label: str, *, title: str | None = None, strike: bool = False) -> str:
    return pill(label, color=Color.GREY, title=title, strike=strike)


def required_pill() -> str:
    return pill_red("required")


def deprecated_pill() -> str:
    return pill_grey("deprecated", strike=True)


def internal_pill() -> str:
    return pill_amber("internal")


def content_type_pill(value: str) -> str:
    return pill_orange(value)


def scheme_pill(value: str) -> str:
    return pill_teal(value)


def tag_pills(tags: Iterable[Any]) -> list[str]:
    if not tags:
        return []
    return [" ".join(
        pill_indigo(tag.name, title=tag.description or None) for tag in tags
    )]
