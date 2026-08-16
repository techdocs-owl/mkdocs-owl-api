"""
The OpenAPI model: `types` describes a document, `parser` reads one.

`parse_document` is the entry point; the dataclasses are imported from
`.types` directly, so a reader of an import line can tell the two apart.
"""

from .parser import parse_document

__all__ = ["parse_document"]
