# Specification Page

Turn any Markdown page into a rendered API reference by adding a single
`techdocs-owl:` frontmatter key. Its `type:` selects the flavour - `openapi`
for an [OpenAPI](https://www.openapis.org) 3 spec, `asyncapi` for an
[AsyncAPI](https://www.asyncapi.com) 2 or 3 spec, `jsonschema` for a standalone
[JSON Schema](https://json-schema.org) document. The plugin reads the spec at
build time and writes the reference body into the page.

`techdocs-owl:` is shared across the TechDocs Owl plugin family, so a `type:`
this plugin does not handle is left untouched for a sibling plugin to render.

## Minimal form

`type:` and `spec:` are the only required keys - everything else falls back to
the site-wide defaults:

```markdown
---
techdocs-owl:
  type: openapi
  spec: https://petstore3.swagger.io/api/v3/openapi.json
---
```

```markdown
---
techdocs-owl:
  type: asyncapi
  spec: ../specs/asyncapi.yml
---
```

## With options

Add any of the keys below alongside `type:` and `spec:`:

```markdown
---
techdocs-owl:
  type: openapi
  spec: ../specs/openapi.yml
  title: My REST API
  intro: One-paragraph intro shown above the spec body.
---
```

```markdown
---
techdocs-owl:
  type: asyncapi
  spec: https://schema.example.com/my-service-asyncapi
  title: My Service Events
  intro: One-paragraph intro shown above the spec body.
---
```

# Common Configuration

Following options apply to every `type:`.
Example:

```markdown
---
techdocs-owl:
  type: openapi
  spec: ../specs/openapi.yml
  title: My REST API
  intro: One-paragraph intro shown above the spec body.
  hide_version: false
  hide_internal: false
  hide_download_link: false
  schema_depth: 3
  attachments:
    - ../specs/postman-collection.json
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
| `hide_download_link` | bool | `false` | Hide the spec download link. |
| `schema_depth` | int | `3` | Depth of dot-path flattening for nested object properties. |
| `attachments` | list | - | Extra files to copy and list in the attachments table. See [Attachments](#attachments). |

# Attachments

Specs rarely travel alone. Attachments let you ship companion files -
Postman collections, client SDK bundles, `.proto` definitions, extra
schemas - right next to the reference. Each one is copied into the build
output and listed in the page's attachments table alongside the spec
source, so readers get everything from a single page.

`attachments` is a list. Each entry is either a bare path/URL string, or
a mapping with a `path:` plus optional `title:` and `description:`:

| Key | Type | Default | Effect |
|---|---|---|---|
| `path` | string | - | **Required.** Path or URL to the file. |
| `title` | string | file name | Link label in the **Attachment** column. |
| `description` | string | empty | Text for the **Description** column. |

```markdown
---
techdocs-owl:
  type: openapi
  spec: ../specs/openapi.yml
  attachments:
    - ../specs/postman-collection.json
    - path: ../specs/types.proto
      title: Protobuf definitions
      description: Wire format for the event payloads
    - path: https://example.com/sdk.zip
      title: Client SDK
      description: Generated Python client, version 2.4
---
```

That renders as:

| Attachment | Description |
|---|---|
| :material-file-document: [Specification Source](#) | OpenAPI specification in json format |
| :material-file-document: [postman-collection.json](#) | |
| :material-file-document: [Protobuf definitions](#) | Wire format for the event payloads |
| :material-file-document: [Client SDK](#) | Generated Python client, version 2.4 |

The first row is the spec itself - its description is generated for you
from the spec type and the file format, and the whole row disappears if
you set `hide_download_link: true`. Attachment descriptions are optional;
leave one out and the cell is simply blank.

Paths are resolved relative to the page; URLs are fetched at build time.
If a file can't be read, it's still listed but marked unavailable rather
than failing the build.

# OpenAPI Configuration

`type: openapi` accepts an OpenAPI 3 document and uses only the
[common options](#common-configuration) above - there are no OpenAPI-only keys.

It renders, in order, skipping any section absent from the spec:

1. **Info** - title, version, downloads, description.
2. **Servers** - URLs and server variables.
3. **Endpoints** - grouped by tag; each shows method, path, parameters,
   request body, responses, and security.
4. **Schemas** - property tables with constraints.

See the [Petstore example](examples/petstore.md) for a live render.

# AsyncAPI Configuration

`type: asyncapi` accepts an AsyncAPI 2.x or 3.0 document. On top
of the [common options](#common-configuration), it adds a few keys for
trimming sections that are specific to event-driven specs:

| Key | Type | Default | Effect |
|---|---|---|---|
| `hide_bindings` | bool | `false` | Skip bindings on servers/channels/operations/messages. |
| `hide_traits` | bool | `false` | Skip naming the traits an operation or message applies. |
| `hide_security` | bool | `false` | Skip security admonitions. |

It renders, in order, skipping any section absent from the spec:

1. **Info** - title, version, downloads, license/contact/external docs, description.
2. **Servers** - host, protocol, security, bindings.
3. **Operations** - operation-centric across both AsyncAPI versions
   (2.x `publish`/`subscribe` and 3.0 top-level `operations`), each with the
   parameters of the channel it runs on.
4. **Messages** - headers, payload, examples, bindings.
5. **Schemas** - property tables with constraints.

See the [Streetlight example](examples/streetlight.md) for a live render.

# JSON Schema Configuration

`type: jsonschema` accepts a standalone JSON Schema document - a `.json` or
`.yaml` file whose contents *are* a schema, rather than an API description that
contains schemas. Every dialect from draft-04 to 2020-12 is read; `$schema`
names which, and an unrecognised or missing one is read as 2020-12.

It uses only the [common options](#common-configuration) above, of which
`schema_depth` and `hide_internal` are the ones that bite. There are no
JSON-Schema-only keys.

It renders, in order, skipping any section absent from the document:

1. **Info** - `title` and `description` from the root, the dialect, the
   download link, and `$id` if the document states one. A schema declares no
   version, licence or contact, so those lines never appear.
2. **Schema** - the document's own root: type, composition, property table.
   Omitted for a file that is only definitions.
3. **Definitions** - one section per entry in `$defs` (2019-09 and later) or
   `definitions` (draft-04 through draft-07), with property tables and
   constraints. Every `$ref` elsewhere on the page links to the section here.

See the [Compose Specification example](examples/compose-spec.md) for a live render.
