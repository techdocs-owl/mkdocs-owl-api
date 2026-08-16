"""
The JSON Schema model, in two tiers.

`schema_types` / `schema_parser` are the type system - the only part of any
format model another format may import. `types` / `parser` are the document
layer on top of it, private to this format the way OpenAPI's and AsyncAPI's are.

`parse_document` is the entry point for a standalone `.schema.json`.
"""

from .parser import parse_document

__all__ = ["parse_document"]
