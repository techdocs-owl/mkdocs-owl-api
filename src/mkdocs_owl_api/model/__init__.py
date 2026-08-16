"""
The parse side of the plugin: what a spec *is*, and how to read one.

Nothing under `model/` imports a renderer, so the whole tier can be exercised
without markdown, mkdocs or a page in sight.

This root holds only what no format owns - the `info` metadata every format
spells the same way (`doc_types`, `doc_parser`) and the machinery parsing runs
on (`parse_report`, `parse_refs`, `parse_util`). Everything format-specific
lives in `jsonschema/`, `openapi/`, `asyncapi/`, each of which exports
`parse_document`.

Naming: `*_types` modules hold frozen dataclasses and nothing else; `*_parser`
modules turn raw JSON into them and never raise.
"""
