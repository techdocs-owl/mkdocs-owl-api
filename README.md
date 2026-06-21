# techdocs-owl-api

MkDocs plugin that renders AsyncAPI and OpenAPI specs into reference pages
at build time.

## Install

```bash
pip install mkdocs-owl-api
```

```yaml
# mkdocs.yml
plugins:
  - search
  - owl-api
```

Add a page with a `techdocs-owl-asyncapi:` or `techdocs-owl-openapi:`
frontmatter key and an empty body — the plugin fills it in at build time.

```markdown
---
techdocs-owl-asyncapi: ../specs/asyncapi.yml
---
```

Supports AsyncAPI 2.x/3.0 and OpenAPI 3.x (YAML or JSON), local paths or
HTTP(S) URLs, recursive `$ref` resolution, and a bundled stylesheet
(auto-injected, no `extra_css` setup needed).

## Site-wide defaults

```yaml
plugins:
  - owl-api:
      schema_depth: 3
      hide_internal: false
      hide_bindings: false
      hide_traits: false
      hide_security: false
      hide_version: false
      hide_download_link: false
```

Page frontmatter overrides these per-page.

## AsyncAPI pages

```markdown
---
techdocs-owl-asyncapi:
  spec: https://schema.example.com/my-service-asyncapi
  title: My Service Events
  intro: One-paragraph intro shown above the spec body.
  schema_depth: 3
---
```

| Key | Type | Default | Effect |
|---|---|---|---|
| `spec` | string | — | **Required.** Path or URL to the spec file. |
| `title` | string | `info.title` | Page H1. |
| `intro` | markdown | — | Shown between the title and metadata block. |
| `hide_version` | bool | `false` | Hide the version line. |
| `hide_internal` | bool | `false` | Drop properties marked `x-internal-only: true`. |
| `hide_bindings` | bool | `false` | Skip bindings on servers/channels/operations/messages. |
| `hide_traits` | bool | `false` | Skip trait sections and references. |
| `hide_security` | bool | `false` | Skip security admonitions. |
| `hide_download_link` | bool | `false` | Hide the spec download link. |
| `schema_depth` | int | `3` | Depth of dot-path flattening for nested object properties. |
| `attachments` | list | — | Extra files to copy and list in the downloads table. |

Renders, in order: info, Servers, Operations (operation-centric across
both AsyncAPI versions), Messages, Schemas, Parameters, Traits — sections
absent from the spec are skipped.

## OpenAPI pages

```markdown
---
techdocs-owl-openapi: https://petstore3.swagger.io/api/v3/openapi.json
---
```

| Key | Type | Default | Effect |
|---|---|---|---|
| `spec` | string | — | **Required.** Path or URL to the spec file. |
| `title` | string | `info.title` | Page H1. |
| `intro` | markdown | — | Shown between the title and metadata block. |
| `hide_version` | bool | `false` | Hide the version line. |
| `hide_internal` | bool | `false` | Drop `x-internal-only` properties. |
| `hide_download_link` | bool | `false` | Hide the spec download link. |
| `schema_depth` | int | `3` | Depth of dot-path flattening for nested object properties. |
| `attachments` | list | — | Extra files to copy and list in the downloads table. |

Renders: info, Servers, endpoints grouped by tag (parameters, request
body, responses, security), Schemas.

## Downloads & attachments

The resolved spec (external `$ref`s inlined) is written to
`assets/techdocs-owl-api/<page-slug>.json` and linked from a Downloads
table. Add extra files (e.g. `.proto` schemas) with `attachments`:

```markdown
---
techdocs-owl-asyncapi:
  spec: ../specs/asyncapi.yml
  attachments:
    - path: ../schemas/customer.proto
      title: Customer Protobuf Schema
    - ../schemas/order.proto   # shorthand: path only, title = filename
---
```

## Error handling

Errors (missing/unreadable spec, network failures, parse errors, bad
frontmatter) render as a `!!! danger` admonition instead of failing the
build.

## Development

```bash
uv sync
uv run pytest
```
