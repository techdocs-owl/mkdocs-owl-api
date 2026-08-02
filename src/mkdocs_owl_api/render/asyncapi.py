"""
AsyncAPI 2.x/3.0 page renderer.
"""

from __future__ import annotations

from typing import Any

from ..options import PageOptions
from .common import (
    _anchor,
    _demote_headings,
    _heading,
    _pill,
    _render_bindings,
    _render_downloads_table,
    _render_examples,
    _render_schema,
    _render_security_inline,
    _render_tags,
    _resolve_ref,
    _ref_link,
)


def _render_info_extras(info: dict[str, Any]) -> str:
    """
    Render the metadata.
    Covers `info.license`, `info.contact`, `info.externalDocs`.
    """
    parts: list[str] = []

    license_ = info.get("license")
    if isinstance(license_, dict):
        name = license_.get("name") or "license"
        url = license_.get("url")
        parts.append(f"**License:** [{name}]({url})" if url else f"**License:** {name}")

    contact = info.get("contact")
    if isinstance(contact, dict):
        bits: list[str] = []
        if contact.get("name"):
            bits.append(contact["name"])
        if contact.get("email"):
            bits.append(f"[{contact['email']}](mailto:{contact['email']})")
        if contact.get("url"):
            bits.append(f"[{contact['url']}]({contact['url']})")
        if bits:
            parts.append(f"**Contact:** {', '.join(bits)}")

    ext_docs = info.get("externalDocs")
    if isinstance(ext_docs, dict) and ext_docs.get("url"):
        url = ext_docs["url"]
        desc = ext_docs.get("description") or url
        parts.append(f"**External docs:** [{desc}]({url})")

    if not parts:
        return ""
    parts.append("")
    return "\n".join(parts)


def _render_servers(spec: dict[str, Any], opts: PageOptions) -> str:
    servers = spec.get("servers")
    if not isinstance(servers, dict) or not servers:
        return ""

    parts: list[str] = ["## Servers", ""]
    for sname, server in servers.items():
        if not isinstance(server, dict):
            continue
        parts.append(_heading(3, sname, anchor=_anchor("servers", sname)))
        parts.append("")

        desc = (server.get("description") or "").strip()
        if desc:
            parts.append(_demote_headings(desc))
            parts.append("")

        meta_emitted = False
        host = server.get("host")
        if host:
            parts.append(f"**Host:** `{host}`")
            meta_emitted = True
        protocol = server.get("protocol")
        if protocol:
            parts.append(f"**Protocol:** {_pill(str(protocol), kind='protocol')}")
            meta_emitted = True
        for label, key in (("Protocol version", "protocolVersion"),
                           ("Pathname", "pathname")):
            v = server.get(key)
            if v:
                parts.append(f"**{label}:** `{v}`")
                meta_emitted = True
        if meta_emitted:
            parts.append("")

        tags = _render_tags(server.get("tags"))
        if tags:
            parts.append(tags)
            parts.append("")

        security = server.get("security") or []
        if security and not opts.hide_security:
            for entry in security:
                block = _render_security_inline(spec, entry)
                if block:
                    parts.append(block)
                    parts.append("")

        bindings = _render_bindings(server.get("bindings"), hide_bindings=(opts.hide_bindings))
        if bindings:
            parts.append(bindings)

    return "\n".join(parts)


def _render_message(
    msg: dict[str, Any],
    *,
    name: str | None = None,
    hide_internal: bool,
    hide_bindings: bool,
    hide_traits: bool,
    max_depth: int = 3,
    show_message_id: bool = False,
) -> str:
    parts: list[str] = []

    if show_message_id:
        mid = msg.get("messageId")
        if mid:
            parts.append(f"**Message ID:** `{mid}`")
            parts.append("")

    title = (msg.get("title") or "").strip()
    if title and title != name:
        parts.append(f"_{title}_")
        parts.append("")

    summary = (msg.get("summary") or "").strip()
    if summary:
        parts.append(summary)
        parts.append("")

    desc = (msg.get("description") or "").strip()
    if desc:
        parts.append(_demote_headings(desc))
        parts.append("")

    ct = msg.get("contentType")
    if ct:
        parts.append(f"**Content type:** {_pill(str(ct), kind='contenttype')}")
        parts.append("")

    tags = _render_tags(msg.get("tags"))
    if tags:
        parts.append(tags)
        parts.append("")

    headers = msg.get("headers")
    if isinstance(headers, dict):
        parts.append("**Headers**")
        parts.append("")
        parts.append(_render_schema(headers, hide_internal=hide_internal, max_depth=max_depth))
        parts.append("")

    payload = msg.get("payload")
    if isinstance(payload, dict):
        parts.append("**Payload**")
        parts.append("")
        parts.append(_render_schema(payload, hide_internal=hide_internal, max_depth=max_depth))
        parts.append("")

    traits = msg.get("traits") or []
    if traits and not hide_traits:
        parts.append("**Traits:**")
        parts.append("")
        for t in traits:
            if isinstance(t, dict) and "$ref" in t:
                parts.append(f"- {_ref_link(t['$ref'])}")
        parts.append("")

    examples = msg.get("examples")
    if examples:
        ex_block = _render_examples(examples)
        if ex_block:
            parts.append(ex_block)

    bindings = _render_bindings(msg.get("bindings"), hide_bindings=hide_bindings)
    if bindings:
        parts.append(bindings)

    return "\n".join(parts).strip()


def _render_v2_operation(
    op: dict[str, Any],
    *,
    action: str,
    channel_name: str,
    channel: dict[str, Any],
    hide_internal: bool,
    hide_bindings: bool,
    hide_traits: bool,
    max_depth: int = 3,
) -> str:
    op_id = op.get("operationId") or f"{action} {channel_name}"
    parts: list[str] = [_heading(3, op_id, anchor=_anchor("operations", op_id)), ""]

    parts.append(f"**Action:** {_pill(action, kind=f'action-{action}')}")
    parts.append("")

    summary = (op.get("summary") or "").strip()
    if summary:
        parts.append(summary)
        parts.append("")

    desc = (op.get("description") or "").strip()
    if desc:
        parts.append(_demote_headings(desc))
        parts.append("")

    tags = _render_tags(op.get("tags"))
    if tags:
        parts.append(tags)
        parts.append("")

    addr = channel.get("address") or channel_name
    parts.append(f"**Channel:** `{addr}`")
    parts.append("")

    params = channel.get("parameters") or {}
    if isinstance(params, dict) and params:
        parts.append("**Parameters:**")
        parts.append("")
        for pname, p in params.items():
            if isinstance(p, dict) and "$ref" in p:
                parts.append(f"- `{pname}` — {_ref_link(p['$ref'])}")
            elif isinstance(p, dict):
                pdesc = (p.get("description") or "").strip()
                parts.append(f"- `{pname}`" + (f" — {pdesc}" if pdesc else ""))
            else:
                parts.append(f"- `{pname}`")
        parts.append("")

    msg = op.get("message") or {}
    messages = msg.get("oneOf", [msg] if msg and "oneOf" not in msg else [])
    for m in messages:
        if not isinstance(m, dict):
            continue
        if "$ref" in m:
            parts.append(f"**Message:** {_ref_link(m['$ref'])}")
            parts.append("")
            continue
        mname = m.get("name") or m.get("title") or "Message"
        parts.append(f"**Message: {mname}**")
        parts.append("")
        parts.append(_render_message(
            m, name=mname,
            hide_internal=hide_internal, hide_bindings=hide_bindings,
            hide_traits=hide_traits, max_depth=max_depth,
        ))
        parts.append("")

    bindings = _render_bindings(op.get("bindings"), hide_bindings=hide_bindings)
    if bindings:
        parts.append(bindings)

    return "\n".join(parts)


def _render_operations_v2(spec: dict[str, Any], opts: PageOptions) -> str:
    channels = spec.get("channels")
    if not isinstance(channels, dict) or not channels:
        return ""

    parts: list[str] = ["## Operations", ""]
    emitted = False
    for cname, channel in channels.items():
        if not isinstance(channel, dict):
            continue
        for action in ("publish", "subscribe"):
            op = channel.get(action)
            if not isinstance(op, dict):
                continue
            parts.append(_render_v2_operation(
                op,
                action=action,
                channel_name=cname,
                channel=channel,
                hide_internal=(opts.hide_internal),
                hide_bindings=(opts.hide_bindings),
                hide_traits=(opts.hide_traits),
                max_depth=(opts.schema_depth),
            ))
            parts.append("")
            emitted = True

    return "\n".join(parts) if emitted else ""


def _render_operations(spec: dict[str, Any], opts: PageOptions) -> str:
    """Render the `## Operations` section with one `### opName` per operation.

    AsyncAPI 3.0 has a top-level `operations` map, rendered as is.
    AsyncAPI 2.x collects from `publish`/`subscribe`
    """
    ops = spec.get("operations")
    if not isinstance(ops, dict) or not ops:
        return _render_operations_v2(spec, opts)

    parts: list[str] = ["## Operations", ""]
    for oname, op in ops.items():
        if not isinstance(op, dict):
            continue
        parts.append(_heading(3, oname, anchor=_anchor("operations", oname)))
        parts.append("")

        action = op.get("action")
        if action:
            kind = "action-send" if action == "send" else "action-receive"
            line = f"**Action:** {_pill(str(action), kind=kind)}"
            if op.get("deprecated"):
                line += " " + _pill("deprecated", kind="deprecated")
            parts.append(line)
            parts.append("")

        summary = (op.get("summary") or "").strip()
        if summary:
            parts.append(summary)
            parts.append("")

        desc = (op.get("description") or "").strip()
        if desc:
            parts.append(_demote_headings(desc))
            parts.append("")

        tags = _render_tags(op.get("tags"))
        if tags:
            parts.append(tags)
            parts.append("")

        ch = op.get("channel")
        if isinstance(ch, dict) and "$ref" in ch:
            resolved = _resolve_ref(spec, ch["$ref"])
            if isinstance(resolved, dict) and resolved.get("address"):
                parts.append(f"**Channel:** `{resolved['address']}`")
            else:
                parts.append(f"**Channel:** `{ch['$ref'].rsplit('/', 1)[-1]}`")
            parts.append("")

        msgs = op.get("messages") or []
        if isinstance(msgs, list) and msgs:
            parts.append("**Messages:**")
            parts.append("")
            for m in msgs:
                if isinstance(m, dict) and "$ref" in m:
                    parts.append(f"- {_ref_link(m['$ref'])}")
            parts.append("")

        traits = op.get("traits") or []
        if traits and not opts.hide_traits:
            parts.append("**Traits:**")
            parts.append("")
            for t in traits:
                if isinstance(t, dict) and "$ref" in t:
                    parts.append(f"- {_ref_link(t['$ref'])}")
            parts.append("")

        bindings = _render_bindings(op.get("bindings"), hide_bindings=(opts.hide_bindings))
        if bindings:
            parts.append(bindings)

    return "\n".join(parts)


def _render_messages(spec: dict[str, Any], opts: PageOptions) -> str:
    msgs = (spec.get("components") or {}).get("messages")
    if not isinstance(msgs, dict) or not msgs:
        return ""

    parts: list[str] = ["## Messages", ""]
    for mname, msg in msgs.items():
        if not isinstance(msg, dict):
            continue
        parts.append(_heading(3, mname, anchor=_anchor("messages", mname)))
        parts.append("")
        parts.append(_render_message(
            msg, name=mname,
            hide_internal=(opts.hide_internal), hide_bindings=(opts.hide_bindings),
            hide_traits=(opts.hide_traits), max_depth=(opts.schema_depth), show_message_id=True,
        ))
        parts.append("")

    return "\n".join(parts)


def _render_schemas_section(spec: dict[str, Any], opts: PageOptions) -> str:
    schemas = (spec.get("components") or {}).get("schemas")
    if not isinstance(schemas, dict) or not schemas:
        return ""

    parts: list[str] = ["## Schemas", ""]
    for sname, sch in schemas.items():
        if not isinstance(sch, dict):
            continue
        parts.append(_heading(3, sname, anchor=_anchor("schemas", sname)))
        parts.append("")
        parts.append(_render_schema(sch, hide_internal=(opts.hide_internal), max_depth=(opts.schema_depth)))
        parts.append("")
    return "\n".join(parts)


def _render_parameters(spec: dict[str, Any], opts: PageOptions) -> str:
    params = (spec.get("components") or {}).get("parameters")
    if not isinstance(params, dict) or not params:
        return ""

    parts: list[str] = ["## Parameters", ""]
    for pname, p in params.items():
        if not isinstance(p, dict):
            continue
        parts.append(_heading(3, pname, anchor=_anchor("parameters", pname)))
        parts.append("")

        desc = (p.get("description") or "").strip()
        if desc:
            parts.append(_demote_headings(desc))
            parts.append("")

        enum = p.get("enum")
        if enum:
            parts.append("**Allowed values:**")
            parts.append("")
            for v in enum:
                parts.append(f"- `{v}`")
            parts.append("")

        default = p.get("default")
        if default is not None:
            parts.append(f"**Default:** `{default}`")
            parts.append("")

    return "\n".join(parts)


def _render_traits(
    spec: dict[str, Any],
    opts: PageOptions,
    *,
    container: str,
    heading: str,
) -> str:
    if opts.hide_traits:
        return ""
    traits = (spec.get("components") or {}).get(container)
    if not isinstance(traits, dict) or not traits:
        return ""

    parts: list[str] = [f"## {heading}", ""]
    for tname, trait in traits.items():
        if not isinstance(trait, dict):
            continue
        parts.append(_heading(3, tname, anchor=_anchor(container, tname)))
        parts.append("")

        desc = (trait.get("description") or "").strip()
        if desc:
            parts.append(_demote_headings(desc))
            parts.append("")

        ct = trait.get("contentType")
        if ct:
            parts.append(f"**Content type:** {_pill(str(ct), kind='contenttype')}")
            parts.append("")

        headers = trait.get("headers")
        if isinstance(headers, dict):
            parts.append("**Headers**")
            parts.append("")
            parts.append(_render_schema(headers, hide_internal=(opts.hide_internal), max_depth=(opts.schema_depth)))
            parts.append("")

    return "\n".join(parts)


def _render_page(
    spec: dict[str, Any],
    opts: PageOptions,
    *,
    spec_url: str = "",
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    """Render the full AsyncAPI page Markdown from a spec + page options."""
    info = spec.get("info") or {}
    title = (opts.title or info.get("title") or "API Reference").strip()
    intro = opts.intro
    version = (info.get("version") or "").strip()
    description = (info.get("description") or "").strip()

    parts: list[str] = [f"# {title}", ""]

    if intro:
        parts.append(intro)
        parts.append("")

    if version and not opts.hide_version:
        parts.append(f"**Version:** `{version}`")
        parts.append("")

    downloads = _render_downloads_table(
        spec_url, attachments or [], hide_download=(opts.hide_download_link), spec_type="AsyncAPI")
    if downloads:
        parts.append(downloads)

    extras = _render_info_extras(info)
    if extras:
        parts.append(extras)

    dct = spec.get("defaultContentType")
    if dct:
        parts.append(f"**Default content type:** {_pill(str(dct), kind='contenttype')}")
        parts.append("")

    if description:
        parts.append(_demote_headings(description))
        parts.append("")

    sections = [
        _render_servers(spec, opts),
        _render_operations(spec, opts),
        _render_messages(spec, opts),
        _render_schemas_section(spec, opts),
        _render_parameters(spec, opts),
        _render_traits(spec, opts, container="messageTraits", heading="Message traits"),
        _render_traits(spec, opts, container="operationTraits", heading="Operation traits"),
    ]
    for section in sections:
        if section:
            parts.append(section)

    while parts and parts[-1] in ("", "---"):
        parts.pop()

    return "\n".join(parts)
