# Getting started

## Install

```bash
pip install mkdocs-owl-api
```

Enable the plugin in `mkdocs.yml`:

```yaml
plugins:
  - search
  - owl-api
```

The bundled stylesheet is injected automatically.

## Add a reference page

Create a Markdown page with a `techdocs-owl:` frontmatter key and an **empty body**.
The `type:` key selects the spec flavour - `openapi`, `asyncapi` or `jsonschema`.
The plugin fills in the body at build time.

```markdown
---
techdocs-owl:
  type: asyncapi
  spec: ../specs/asyncapi.yml
---
```

The spec reference can be a **local path** (relative to the page) or an **HTTP(S) URL**, in YAML or JSON.

## Build

```bash
mkdocs build
```

## Error handling

Missing or unreadable specs, network failures, parse errors, and malformed
frontmatter all render as a `!!! danger` admonition on the page rather than
aborting the build.

## Requires

- **Python**: 3.9+
- **MkDocs**: 1.6+
- **PyYAML**: 6.0+
- **Markdown**: 3.4+
