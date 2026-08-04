"""
Part builders shared by both flavours.

The abstract bases live in `base.py`; the page preamble (title, intro, version)
is `PageBuilder`'s, not a builder of its own.
"""

from __future__ import annotations

from typing import Any

from .base import BlockBuilder, RenderContext
from .primitives import (
    _anchor,
    _closed_object_note,
    _demote_headings,
    _file_format,
    _format_type,
    _heading,
    _html_table,
    _infer_enum_type,
    _pill,
    _ref_link,
    _render_property_row,
    _resolve_ref,
    _table_cell,
)


class InfoExtrasBuilder(BlockBuilder):
    """
    `info.license`, `info.contact`, `info.externalDocs`.
    """

    @staticmethod
    def _license(license_dict: Any) -> list[str]:
        if not isinstance(license_dict, dict):
            return []
        name = license_dict.get("name") or "license"
        url = license_dict.get("url")
        target = f"[{name}]({url})" if url else name
        return [f":material-scale-balance: **License:** {target}"]

    @staticmethod
    def _contact(contact_dict: Any) -> list[str]:
        if not isinstance(contact_dict, dict):
            return []
        bits: list[str] = []
        if contact_dict.get("name"):
            bits.append(contact_dict["name"])
        if contact_dict.get("email"):
            bits.append(f"[{contact_dict['email']}](mailto:{contact_dict['email']})")
        if contact_dict.get("url"):
            bits.append(f"[{contact_dict['url']}]({contact_dict['url']})")
        return [f":material-contacts: **Contact:** {', '.join(bits)}"] if bits else []

    @staticmethod
    def _external_docs(*candidates: Any) -> list[str]:
        """
        AsyncAPI hangs `externalDocs` off `info`, OpenAPI off the document root
        """
        for ext_docs in candidates:
            if isinstance(ext_docs, dict) and ext_docs.get("url"):
                url = ext_docs["url"]
                desc = ext_docs.get("description") or url
                return [f":material-link-variant: **External documentation:** [{desc}]({url})"]
        return []

    def build(self) -> list[str]:
        info = self.ctx.info
        lines: list[str] = []
        lines.extend(self._license(info.get("license")))
        lines.extend(self._contact(info.get("contact")))
        lines.extend(self._external_docs(
            info.get("externalDocs"), self.spec.get("externalDocs"),
        ))
        return lines


class InfoDescriptionBuilder(BlockBuilder):
    """`info.description`, demoted so its headings nest under the page title."""

    def build(self) -> list[str]:
        desc = (self.ctx.info.get("description") or "").strip()
        return [_demote_headings(desc)] if desc else []


class SchemaTableBuilder(BlockBuilder):
    """
    JSON Schema in, HTML property table out.
    """

    HEADERS = ("Name", "Type", "Description")

    def __init__(self, ctx: RenderContext, schema: dict[str, Any]):
        super().__init__(ctx)
        self._schema = schema if isinstance(schema, dict) else {}
        # Constant for the whole traversal, so they are fields. `prefix` and
        # `depth` vary per step and stay call parameters - promoting them to
        # fields would mean mutating and restoring on unwind.
        self._hide_internal = ctx.options.hide_internal
        self._max_depth = ctx.options.schema_depth

    def rows(self) -> list[tuple[str, dict[str, Any], bool, str | None]]:
        """
        The flattened `(path, schema, required, type_override)` rows, before
        they become cells. Separate from `build` so the traversal can be
        exercised without going through HTML.
        """
        properties = self._schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            return []
        return self._walk(properties, set(self._schema.get("required") or []))

    def build(self) -> list[str]:
        rows = self.rows()
        if not rows:
            return []
        cells = [
            _render_property_row(path, prop, required=req, type_override=override)
            for path, prop, req, override in rows
        ]
        return [_html_table(self.HEADERS, cells)]

    def _walk(
        self,
        properties: dict[str, Any],
        required: set[str],
        *,
        prefix: str = "",
        depth: int = 1,
    ) -> list[tuple[str, dict[str, Any], bool, str | None]]:
        rows: list[tuple[str, dict[str, Any], bool, str | None]] = []
        for pname, pschema in properties.items():
            if not isinstance(pschema, dict):
                continue
            if self._hide_internal and pschema.get("x-internal-only") is True:
                continue

            path = f"{prefix}{pname}"
            req = pname in required
            child_props = pschema.get("properties")
            is_inline_object = (
                "$ref" not in pschema
                and isinstance(child_props, dict) and child_props
            )
            items = pschema.get("items") if pschema.get("type") == "array" else None
            item_props = items.get("properties") if isinstance(items, dict) else None
            is_array_of_objects = (
                isinstance(items, dict) and "$ref" not in items
                and isinstance(item_props, dict) and item_props
            )

            if is_inline_object and depth < self._max_depth:
                rows.append((path, pschema, req, None))
                rows.extend(self._walk(
                    child_props, set(pschema.get("required") or []),
                    prefix=f"{path}.", depth=depth + 1,
                ))
            elif is_array_of_objects and depth < self._max_depth:
                rows.append((f"{path}[]", pschema, req, "array of objects"))
                rows.extend(self._walk(
                    item_props, set(items.get("required") or []),
                    prefix=f"{path}[].", depth=depth + 1,
                ))
            else:
                rows.append((path, pschema, req, None))
        return rows


class SchemaBuilder(BlockBuilder):
    """
    One schema: description, type, composition keywords, property table.
    """

    def __init__(self, ctx: RenderContext, schema: dict[str, Any]):
        super().__init__(ctx)
        self._schema = schema if isinstance(schema, dict) else {}

    def build(self) -> list[str]:
        schema = self._schema
        blocks: list[str] = []

        desc = (schema.get("description") or "").strip()
        if desc:
            blocks.append(_demote_headings(desc))

        if "$ref" in schema:
            blocks.append(f"_Type:_ {_ref_link(schema['$ref'])}")
            return blocks

        note = _closed_object_note(schema)
        if note:
            blocks.append(note)

        type_name = schema.get("type")
        enum = schema.get("enum")
        if not type_name:
            type_name = _infer_enum_type(enum)

        # `allOf` merging feeds the property table, so composition has to be
        # resolved before the enum short-circuit reads `base_props`.
        base_props: dict[str, Any] = dict(schema.get("properties") or {})
        base_required: set[str] = set(schema.get("required") or [])
        compose_lines = self._compose(schema, base_props, base_required)

        if enum and not base_props:
            if type_name:
                blocks.append(f"_Type:_ `{type_name}`")
            blocks.append("**Allowed values:**")
            blocks.append("\n".join(f"- `{v}`" for v in enum))
            return blocks

        if type_name:
            blocks.append(f"_Type:_ `{type_name}`")
        blocks.extend(compose_lines)

        if base_props:
            blocks.append("_Properties:_")
            blocks.extend(SchemaTableBuilder(self.ctx, {
                "properties": base_props,
                "required": sorted(base_required),
            }).build())

        return blocks

    @staticmethod
    def _compose(
        schema: dict[str, Any],
        base_props: dict[str, Any],
        base_required: set[str],
    ) -> list[str]:
        """
        Render `allOf`/`oneOf`/`anyOf` lines, folding inline `allOf` members
        into `base_props` / `base_required` in place.
        """
        lines: list[str] = []

        all_of = schema.get("allOf")
        if isinstance(all_of, list):
            includes: list[str] = []
            for mem in all_of:
                if not isinstance(mem, dict):
                    continue
                if "$ref" in mem:
                    includes.append(_ref_link(mem["$ref"]))
                else:
                    base_props.update(mem.get("properties") or {})
                    base_required.update(mem.get("required") or [])
            if includes:
                lines.append("**All of:** " + " | ".join(includes))

        for kw, label in (("oneOf", "One of"), ("anyOf", "Any of")):
            members = schema.get(kw)
            if isinstance(members, list) and members:
                rendered: list[str] = []
                for mem in members:
                    if isinstance(mem, dict) and "$ref" in mem:
                        rendered.append(_ref_link(mem["$ref"]))
                    elif isinstance(mem, dict):
                        rendered.append(f"`{_format_type(mem)}`")
                    else:
                        rendered.append(f"`{mem}`")
                lines.append(f"**{label}:** " + " | ".join(rendered))

        return lines


class SchemasBuilder(BlockBuilder):
    """
    The `components.schemas` page section. Identical for both flavours.
    """

    def build(self) -> list[str]:
        schemas = (self.spec.get("components") or {}).get("schemas")
        if not isinstance(schemas, dict) or not schemas:
            return []

        blocks: list[str] = ["## Schemas"]
        for name, schema in schemas.items():
            if not isinstance(schema, dict):
                continue
            blocks.append(_heading(3, name, anchor=_anchor("schemas", name)))
            blocks.extend(SchemaBuilder(self.ctx, schema).build())
        return blocks


class SecurityBuilder(BlockBuilder):
    """
    One security requirement, rendered as an admonition. Used inline by both
    flavours - openapi per endpoint, asyncapi per server.
    """

    def __init__(self, ctx: RenderContext, entry: Any):
        super().__init__(ctx)
        self._entry = entry

    def build(self) -> list[str]:
        entry = self._entry
        if not isinstance(entry, dict):
            return []

        scopes: Any = None
        if "$ref" in entry:
            ref = entry["$ref"]
            scheme_name = ref.rsplit("/", 1)[-1]
            scheme = _resolve_ref(self.spec, ref)
        else:
            items = list(entry.items())
            if not items:
                return []
            scheme_name, scopes = items[0]
            components = (self.spec.get("components") or {}).get("securitySchemes") or {}
            scheme = components.get(scheme_name) if isinstance(components, dict) else None

        if not isinstance(scheme, dict):
            return [f"- **Security:** `{scheme_name}`"]

        body: list[str] = []
        scheme_type = scheme.get("type")
        if scheme_type:
            body.append(f"**Type:** {_pill(str(scheme_type), kind='scheme')}")
            body.append("")
        for label, key in (
            ("Name", "name"),
            ("In", "in"),
            ("Scheme", "scheme"),
            ("Bearer format", "bearerFormat"),
            ("OpenID Connect URL", "openIdConnectUrl"),
        ):
            value = scheme.get(key)
            if value:
                body.append(f"**{label}:** `{value}`")

        sdesc = (scheme.get("description") or "").strip()
        if sdesc:
            if body and body[-1] != "":
                body.append("")
            body.append(_demote_headings(sdesc, levels=2))

        if isinstance(scopes, list) and scopes:
            if body and body[-1] != "":
                body.append("")
            body.append("**Scopes:** " + ", ".join(f"`{sc}`" for sc in scopes))

        indented = "\n".join(("    " + line) if line else "" for line in body)
        return [
            f'!!! note ":material-security: Security: {scheme_name}"\n{indented}'
        ]
