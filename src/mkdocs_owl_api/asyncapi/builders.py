"""
AsyncAPI-specific part builders.

`servers` here is a **dict** keyed by server name; the OpenAPI one is a list of
`{url, description, variables}`. The two share nothing but the word, which is
why both packages can own a `ServersBuilder`.
"""

from __future__ import annotations

from typing import Any

from ..common.base import BlockBuilder, RenderContext
from ..common.builders import SchemaBuilder, SecurityBuilder
from ..common.primitives import (
    _anchor,
    _demote_headings,
    _heading,
    _pill,
    _ref_link,
    _render_bindings,
    _render_examples,
    _render_tags,
    _resolve_ref,
)


class ServersBuilder(BlockBuilder):
    """The `## Servers` section. `servers` is a dict keyed by server name."""

    def build(self) -> list[str]:
        servers = self.spec.get("servers")
        if not isinstance(servers, dict) or not servers:
            return []

        blocks: list[str] = ["## Servers"]
        for name, server in servers.items():
            if not isinstance(server, dict):
                continue
            blocks.append(_heading(3, name, anchor=_anchor("servers", name)))

            desc = (server.get("description") or "").strip()
            if desc:
                blocks.append(_demote_headings(desc))

            # One block, so no `meta_emitted` flag is needed to decide whether
            # a trailing blank line belongs here.
            meta: list[str] = []
            host = server.get("host")
            if host:
                meta.append(f"**Host:** `{host}`")
            protocol = server.get("protocol")
            if protocol:
                meta.append(f"**Protocol:** {_pill(str(protocol), kind='protocol')}")
            for label, key in (
                ("Protocol version", "protocolVersion"),
                ("Pathname", "pathname"),
            ):
                value = server.get(key)
                if value:
                    meta.append(f"**{label}:** `{value}`")
            if meta:
                blocks.append("\n".join(meta))

            tags = _render_tags(server.get("tags"))
            if tags:
                blocks.append(tags)

            if not self.options.hide_security:
                for entry in server.get("security") or []:
                    blocks.extend(SecurityBuilder(self.ctx, entry).build())

            bindings = _render_bindings(
                server.get("bindings"), hide_bindings=self.options.hide_bindings,
            )
            if bindings:
                blocks.append(bindings)

        return blocks


class MessageBuilder(BlockBuilder):
    """
    One message.

    Reached from two directions - the `## Messages` section and inline inside a
    2.x operation - which is why it exists separately from `MessagesBuilder`.
    """

    def __init__(
        self,
        ctx: RenderContext,
        message: dict[str, Any],
        *,
        name: str | None = None,
        show_message_id: bool = False,
    ):
        super().__init__(ctx)
        self._message = message if isinstance(message, dict) else {}
        self._name = name
        self._show_message_id = show_message_id

    def build(self) -> list[str]:
        msg = self._message
        opts = self.options
        blocks: list[str] = []

        if self._show_message_id:
            message_id = msg.get("messageId")
            if message_id:
                blocks.append(f"**Message ID:** `{message_id}`")

        title = (msg.get("title") or "").strip()
        if title and title != self._name:
            blocks.append(f"_{title}_")

        summary = (msg.get("summary") or "").strip()
        if summary:
            blocks.append(summary)

        desc = (msg.get("description") or "").strip()
        if desc:
            blocks.append(_demote_headings(desc))

        content_type = msg.get("contentType")
        if content_type:
            blocks.append(
                f"**Content type:** {_pill(str(content_type), kind='contenttype')}"
            )

        tags = _render_tags(msg.get("tags"))
        if tags:
            blocks.append(tags)

        for label, key in (("**Headers**", "headers"), ("**Payload**", "payload")):
            schema = msg.get(key)
            if isinstance(schema, dict):
                blocks.append(label)
                blocks.extend(SchemaBuilder(self.ctx, schema).build())

        traits = msg.get("traits") or []
        if traits and not opts.hide_traits:
            refs = [
                f"- {_ref_link(t['$ref'])}"
                for t in traits if isinstance(t, dict) and "$ref" in t
            ]
            blocks.append("**Traits:**")
            if refs:
                blocks.append("\n".join(refs))

        examples = msg.get("examples")
        if examples:
            rendered = _render_examples(examples)
            if rendered:
                blocks.append(rendered)

        bindings = _render_bindings(
            msg.get("bindings"), hide_bindings=opts.hide_bindings,
        )
        if bindings:
            blocks.append(bindings)

        return blocks


class MessagesBuilder(BlockBuilder):
    """The `## Messages` section, from `components.messages`."""

    def build(self) -> list[str]:
        messages = (self.spec.get("components") or {}).get("messages")
        if not isinstance(messages, dict) or not messages:
            return []

        blocks: list[str] = ["## Messages"]
        for name, msg in messages.items():
            if not isinstance(msg, dict):
                continue
            blocks.append(_heading(3, name, anchor=_anchor("messages", name)))
            blocks.extend(
                MessageBuilder(self.ctx, msg, name=name, show_message_id=True).build()
            )
        return blocks


class OperationsBuilder(BlockBuilder):
    """
    The `## Operations` section.

    A spec-version fork rather than a runtime condition: 3.0 has a top-level
    `operations` map, 2.x collects `publish`/`subscribe` off each channel. Two
    builders behind one entry point keeps either side readable.
    """

    def build(self) -> list[str]:
        operations = self.spec.get("operations")
        if isinstance(operations, dict) and operations:
            return _V3OperationsBuilder(self.ctx).build()
        return _V2OperationsBuilder(self.ctx).build()


class _V3OperationsBuilder(BlockBuilder):
    """AsyncAPI 3.0: a top-level `operations` map, rendered as is."""

    def build(self) -> list[str]:
        operations = self.spec.get("operations")
        if not isinstance(operations, dict) or not operations:
            return []

        blocks: list[str] = ["## Operations"]
        for name, op in operations.items():
            if not isinstance(op, dict):
                continue
            blocks.append(_heading(3, name, anchor=_anchor("operations", name)))
            blocks.extend(self._operation(op))
        return blocks

    def _operation(self, op: dict[str, Any]) -> list[str]:
        opts = self.options
        blocks: list[str] = []

        action = op.get("action")
        if action:
            kind = "action-send" if action == "send" else "action-receive"
            line = f"**Action:** {_pill(str(action), kind=kind)}"
            if op.get("deprecated"):
                line += " " + _pill("deprecated", kind="deprecated")
            blocks.append(line)

        summary = (op.get("summary") or "").strip()
        if summary:
            blocks.append(summary)

        desc = (op.get("description") or "").strip()
        if desc:
            blocks.append(_demote_headings(desc))

        tags = _render_tags(op.get("tags"))
        if tags:
            blocks.append(tags)

        channel = op.get("channel")
        if isinstance(channel, dict) and "$ref" in channel:
            resolved = _resolve_ref(self.spec, channel["$ref"])
            if isinstance(resolved, dict) and resolved.get("address"):
                blocks.append(f"**Channel:** `{resolved['address']}`")
            else:
                blocks.append(
                    f"**Channel:** `{channel['$ref'].rsplit('/', 1)[-1]}`"
                )

        blocks.extend(self._ref_list("**Messages:**", op.get("messages") or []))
        if not opts.hide_traits:
            blocks.extend(self._ref_list("**Traits:**", op.get("traits") or []))

        bindings = _render_bindings(
            op.get("bindings"), hide_bindings=opts.hide_bindings,
        )
        if bindings:
            blocks.append(bindings)

        return blocks

    @staticmethod
    def _ref_list(label: str, entries: Any) -> list[str]:
        if not isinstance(entries, list) or not entries:
            return []
        refs = [
            f"- {_ref_link(e['$ref'])}"
            for e in entries if isinstance(e, dict) and "$ref" in e
        ]
        return [label, "\n".join(refs)] if refs else [label]


class _V2OperationsBuilder(BlockBuilder):
    """AsyncAPI 2.x: `publish`/`subscribe` collected off each channel."""

    def build(self) -> list[str]:
        channels = self.spec.get("channels")
        if not isinstance(channels, dict) or not channels:
            return []

        body: list[str] = []
        for channel_name, channel in channels.items():
            if not isinstance(channel, dict):
                continue
            for action in ("publish", "subscribe"):
                op = channel.get(action)
                if not isinstance(op, dict):
                    continue
                body.extend(self._operation(
                    op, action=action, channel_name=channel_name, channel=channel,
                ))

        # No publish/subscribe anywhere means no section at all, not an empty
        # heading - the `emitted` flag the old renderer carried for this.
        return ["## Operations", *body] if body else []

    def _operation(
        self,
        op: dict[str, Any],
        *,
        action: str,
        channel_name: str,
        channel: dict[str, Any],
    ) -> list[str]:
        opts = self.options
        op_id = op.get("operationId") or f"{action} {channel_name}"
        blocks: list[str] = [
            _heading(3, op_id, anchor=_anchor("operations", op_id)),
            f"**Action:** {_pill(action, kind=f'action-{action}')}",
        ]

        summary = (op.get("summary") or "").strip()
        if summary:
            blocks.append(summary)

        desc = (op.get("description") or "").strip()
        if desc:
            blocks.append(_demote_headings(desc))

        tags = _render_tags(op.get("tags"))
        if tags:
            blocks.append(tags)

        blocks.append(f"**Channel:** `{channel.get('address') or channel_name}`")

        params = channel.get("parameters") or {}
        if isinstance(params, dict) and params:
            bullets: list[str] = []
            for pname, param in params.items():
                if isinstance(param, dict) and "$ref" in param:
                    bullets.append(f"- `{pname}` — {_ref_link(param['$ref'])}")
                elif isinstance(param, dict):
                    pdesc = (param.get("description") or "").strip()
                    bullets.append(f"- `{pname}`" + (f" — {pdesc}" if pdesc else ""))
                else:
                    bullets.append(f"- `{pname}`")
            blocks.append("**Parameters:**")
            blocks.append("\n".join(bullets))

        message = op.get("message") or {}
        members = message.get("oneOf", [message] if message and "oneOf" not in message else [])
        for member in members:
            if not isinstance(member, dict):
                continue
            if "$ref" in member:
                blocks.append(f"**Message:** {_ref_link(member['$ref'])}")
                continue
            name = member.get("name") or member.get("title") or "Message"
            blocks.append(f"**Message: {name}**")
            blocks.extend(MessageBuilder(self.ctx, member, name=name).build())

        bindings = _render_bindings(
            op.get("bindings"), hide_bindings=opts.hide_bindings,
        )
        if bindings:
            blocks.append(bindings)

        return blocks


class ParametersBuilder(BlockBuilder):
    """The `## Parameters` section, from `components.parameters`."""

    def build(self) -> list[str]:
        params = (self.spec.get("components") or {}).get("parameters")
        if not isinstance(params, dict) or not params:
            return []

        blocks: list[str] = ["## Parameters"]
        for name, param in params.items():
            if not isinstance(param, dict):
                continue
            blocks.append(_heading(3, name, anchor=_anchor("parameters", name)))

            desc = (param.get("description") or "").strip()
            if desc:
                blocks.append(_demote_headings(desc))

            enum = param.get("enum")
            if enum:
                blocks.append("**Allowed values:**")
                blocks.append("\n".join(f"- `{v}`" for v in enum))

            default = param.get("default")
            if default is not None:
                blocks.append(f"**Default:** `{default}`")

        return blocks


class TraitsBuilder(BlockBuilder):
    """`components.messageTraits` or `components.operationTraits`."""

    def __init__(self, ctx: RenderContext, *, container: str, heading: str):
        super().__init__(ctx)
        self._container = container
        self._heading = heading

    def build(self) -> list[str]:
        if self.options.hide_traits:
            return []
        traits = (self.spec.get("components") or {}).get(self._container)
        if not isinstance(traits, dict) or not traits:
            return []

        blocks: list[str] = [f"## {self._heading}"]
        for name, trait in traits.items():
            if not isinstance(trait, dict):
                continue
            blocks.append(_heading(3, name, anchor=_anchor(self._container, name)))

            desc = (trait.get("description") or "").strip()
            if desc:
                blocks.append(_demote_headings(desc))

            content_type = trait.get("contentType")
            if content_type:
                blocks.append(
                    f"**Content type:** {_pill(str(content_type), kind='contenttype')}"
                )

            headers = trait.get("headers")
            if isinstance(headers, dict):
                blocks.append("**Headers**")
                blocks.extend(SchemaBuilder(self.ctx, headers).build())

        return blocks


class DefaultContentTypeBuilder(BlockBuilder):
    """The spec-level `defaultContentType`."""

    def build(self) -> list[str]:
        value = self.spec.get("defaultContentType")
        if not value:
            return []
        return [f"**Default content type:** {_pill(str(value), kind='contenttype')}"]
