"""
JSON Schema, as one importable unit: `parse_document` and `Renderer`.
"""

from ..model.jsonschema import parse_document
from .render import JsonSchemaRenderer as Renderer

__all__ = ["Renderer", "parse_document"]
