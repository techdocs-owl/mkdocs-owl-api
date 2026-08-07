A [MkDocs](https://www.mkdocs.org) plugin that renders **AsyncAPI** and
**OpenAPI** specs into Markdown reference pages at build time.

Point a page at a spec file with a frontmatter key, leave the body empty,
and the plugin fills it in when you build the site - no manual transcription,
always in sync with the spec.

## Highlights

- **AsyncAPI 2.x / 3.x and OpenAPI 3.x** - YAML or JSON.
- **Local paths or fetch via HTTP(S)**, with recursive external `$ref` resolution.
- **Native MkDocs rendering to keep your styles**.
- **Bundled stylesheet**, auto-injected - no `extra_css` wiring needed.
- **Attachments** - add any extra files alongside your API.
- **Graceful errors** - a bad spec renders a `!!! danger` admonition, no build failing

## Quick look

```markdown
---
techdocs-owl:
  type: openapi
  spec: ../specs/openapi.yml
---
```

That single page becomes a full complete API reference.

See it in action on the [Streetlight (AsyncAPI)](examples/streetlight.md) and [Petstore (OpenAPI)](examples/petstore.md) example pages.

## Next steps

- [Getting started](getting-started.md) - install and add your first page.
- [Customization](customization.md) - frontmatter options for OpenAPI and AsyncAPI specs.

The package is on PyPI as [`mkdocs-owl-api`](https://pypi.org/project/mkdocs-owl-api/).
