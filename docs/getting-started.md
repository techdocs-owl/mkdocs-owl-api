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

Create a Markdown page with a `techdocs-owl-asyncapi:` or `techdocs-owl-openapi:` frontmatter key and an **empty body**. 
The plugin fills in the body at build time.

```markdown
---
techdocs-owl-asyncapi: ../specs/asyncapi.yml
---
```

The spec reference can be a **local path** (relative to the page) or an **HTTP(S) URL**, in YAML or JSON.

## Build

```bash
mkdocs build
```

!!! warning "Don't use `--strict`"
    The plugin writes spec JSON and attachments into the build directory
    after MkDocs has finalized its file collection, so `mkdocs build
    --strict` flags those generated assets as "not found among
    documentation files." Build without `--strict`.

## Error handling

Missing or unreadable specs, network failures, parse errors, and malformed
frontmatter all render as a `!!! danger` admonition on the page rather than
aborting the build.
