"""
OpenAPI, as one importable unit: `parse_document` and `Renderer`.
"""

from .parser import parse_document
from .render import OpenApiRenderer as Renderer

__all__ = ["Renderer", "parse_document"]
