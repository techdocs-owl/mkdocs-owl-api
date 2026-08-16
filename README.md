# techdocs-owl-api

MkDocs plugin that renders AsyncAPI, OpenAPI and JSON Schema specs into
reference pages at build time.

Check out [documentation](https://techdocs-owl.github.io/mkdocs-owl-api/).

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

Add a page with a `techdocs-owl:` frontmatter key naming the spec `type:`
and an empty body - the plugin fills it in at build time.

```markdown
---
techdocs-owl:
  type: asyncapi
  spec: ../specs/asyncapi.yml
---
```

Supports AsyncAPI 2.x/3.x, OpenAPI 3.x and JSON Schema draft-04 through 2020-12
(YAML or JSON), local paths or HTTP(S) URLs, recursive `$ref` resolution, and a
bundled stylesheet (auto-injected, no `extra_css` setup needed).

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
techdocs-owl:
  type: asyncapi
  spec: https://schema.example.com/my-service-asyncapi
  title: My Service Events
  intro: One-paragraph intro shown above the spec body.
  schema_depth: 3
---
```

| Key | Type | Default | Effect |
|---|---|---|---|
| `type` | string | - | **Required.** `openapi`, `asyncapi` or `jsonschema`. |
| `spec` | string | - | **Required.** Path or URL to the spec file. |
| `title` | string | `info.title` | Page H1. |
| `intro` | markdown | - | Shown between the title and metadata block. |
| `hide_version` | bool | `false` | Hide the version line. |
| `hide_internal` | bool | `false` | Drop properties marked `x-internal-only: true`. |
| `hide_bindings` | bool | `false` | Skip bindings on servers/channels/operations/messages. |
| `hide_traits` | bool | `false` | Skip trait sections and references. |
| `hide_security` | bool | `false` | Skip security admonitions. |
| `hide_download_link` | bool | `false` | Hide the spec download link. |
| `schema_depth` | int | `3` | Depth of dot-path flattening for nested object properties. |
| `attachments` | list | - | Extra files to copy and list in the attachments table. |

Renders, in order: info, Servers, Operations (operation-centric across
both AsyncAPI versions), Messages, Schemas, Parameters, Traits - sections
absent from the spec are skipped.

## OpenAPI pages

```markdown
---
techdocs-owl:
  type: openapi
  spec: https://petstore3.swagger.io/api/v3/openapi.json
---
```

| Key | Type | Default | Effect |
|---|---|---|---|
| `type` | string | - | **Required.** `openapi`, `asyncapi` or `jsonschema`. |
| `spec` | string | - | **Required.** Path or URL to the spec file. |
| `title` | string | `info.title` | Page H1. |
| `intro` | markdown | - | Shown between the title and metadata block. |
| `hide_version` | bool | `false` | Hide the version line. |
| `hide_internal` | bool | `false` | Drop `x-internal-only` properties. |
| `hide_download_link` | bool | `false` | Hide the spec download link. |
| `schema_depth` | int | `3` | Depth of dot-path flattening for nested object properties. |
| `attachments` | list | - | Extra files to copy and list in the attachments table. |

Renders: info, Servers, endpoints grouped by tag (parameters, request
body, responses, security), Schemas.

## JSON Schema pages

```markdown
---
techdocs-owl:
  type: jsonschema
  spec: ../schemas/product.json
---
```

A standalone schema document, in any dialect from draft-04 to 2020-12 -
`$schema` names which, and an unrecognised or missing one is read as 2020-12.
Uses the common options above; `schema_depth` and `hide_internal` are the ones
that apply.

Renders: info (`title`, `description`, dialect, `$id`), the root Schema, then
Definitions - one section per `$defs`/`definitions` entry, which every `$ref`
on the page links to. Keywords the plugin does not model are dropped silently;
`patternProperties` is the notable one, so a pattern-keyed map renders as a
plain `object`.

## Attachments

The resolved spec (external `$ref`s inlined) is written to
`assets/techdocs-owl-api/<page-slug>.json` and linked from a table with
**Attachment** and **Description** columns. Its description is generated
("AsyncAPI specification in json format"). Add extra files (e.g. `.proto`
schemas) with `attachments`, each taking an optional `title` and
`description`:

```markdown
---
techdocs-owl:
  type: asyncapi
  spec: ../specs/asyncapi.yml
  attachments:
    - path: ../schemas/customer.proto
      title: Customer Protobuf Schema
      description: Wire format for customer events
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

`uv sync` installs the project itself in editable mode, so `src/` edits
take effect without reinstalling. Docs deps (`mkdocs-material`) come from
the `dev` dependency group, which uv syncs by default.

Build or serve the documentation site:

```bash
uv run mkdocs build       # -> site/
uv run mkdocs serve       # http://127.0.0.1:8000, live reload
```

The example site is a separate mkdocs project:

```bash
uv run mkdocs serve -f example/mkdocs.yml
```
