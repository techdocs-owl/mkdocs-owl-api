"""
AsyncAPI page renderer, driven by the model.

The renderer never learns which dialect the description came from: a 2.x file
and a 3.0 file describing the same API produce the same page - including the
words for what an operation does, which the model states from the application's
point of view.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import yaml

from ..common.render import MarkdownRenderer
from ..common.primitives.markup import (
    _anchor,
    _demote_headings,
    _heading,
    _html_table,
    _md_to_html,
)
from ..common.primitives.pills import (
    content_type_pill,
    deprecated_pill,
    pill_blue,
    pill_grey,
    pill_teal,
    required_pill,
    scheme_pill,
    tag_pills,
)
from ..jsonschema.schema_model import Schema
from ..jsonschema.schema_render import describe, format_type, render_schema
from .model import (
    AsyncApiDoc, Channel, Message, Operation, OperationAction, Server,
)


PARAMETER_HEADERS = ("Name", "Type", "Description")

_ACTION_PILLS = {
    OperationAction.SEND: pill_blue,
    OperationAction.RECEIVE: pill_teal,
}


def action_pill(action: OperationAction) -> str:
    return _ACTION_PILLS.get(action, pill_grey)(action.value)


def _bindings(bindings: dict[str, Any], *, hide: bool) -> list[str]:
    """
    Protocol bindings as fenced YAML.

    A binding's shape belongs to its protocol, so there is nothing to lay out -
    only something to show as written.
    """
    if hide or not bindings:
        return []
    blocks: list[str] = []
    for protocol, body in bindings.items():
        rendered = yaml.safe_dump(body, sort_keys=False,
                                  default_flow_style=False).rstrip()
        indented = "\n".join("    " + line for line in rendered.split("\n"))
        blocks.append(f'!!! note "{protocol} bindings"\n    ```yaml\n{indented}\n    ```')
    return blocks


def _ref_bullets(label: str, names, section: str) -> list[str]:
    if not names:
        return []
    bullets = "\n".join(f"- [`{n}`](#{_anchor(section, n)})" for n in names)
    return [label, bullets]


def _trait_names(names: tuple[str, ...]) -> list[str]:
    """
    The traits that were applied.
    """
    if not names:
        return []
    return ["**Traits:** " + ", ".join(f"`{name}`" for name in names)]


class AsyncApiRenderer(MarkdownRenderer):
    """Servers, operations, messages, schemas."""

    doc: AsyncApiDoc

    def sections(self) -> list[str]:
        return (
            self.default_content_type()
            + self.servers()
            + self.operations()
            + self.messages()
            + self.schemas()
        )

    def default_content_type(self) -> list[str]:
        value = self.doc.default_content_type
        if not value:
            return []
        return [f"**Default content type:** {content_type_pill(value)}"]

    # -- servers ------------------------------------------------------------

    def servers(self) -> list[str]:
        if not self.doc.servers:
            return []
        blocks: list[str] = ["## Servers"]
        for server in self.doc.servers:
            blocks.extend(self.server(server))
        return blocks

    def server(self, server: Server) -> list[str]:
        blocks = [_heading(3, server.name, anchor=_anchor("servers", server.name))]

        # The address carries its own protocol and path, so it is one line.
        if server.url:
            blocks.append(f":material-link-variant: `{server.url}`")
        if server.protocol_version:
            blocks.append(f"**Protocol version:** `{server.protocol_version}`")
        if server.description:
            blocks.append(_demote_headings(server.description.strip()))

        blocks.extend(tag_pills(server.tags))
        for name, variable in server.variables.items():
            bits = []
            if variable.default:
                bits.append(f"default `{variable.default}`")
            if variable.enum:
                bits.append("one of " + ", ".join(f"`{v}`" for v in variable.enum))
            if variable.description:
                bits.append(variable.description.strip())
            suffix = (" — " + "; ".join(bits)) if bits else ""
            blocks.append(f"- `{{{name}}}`{suffix}")

        if not self.options.hide_security:
            for alternative in server.security:
                for requirement in alternative:
                    blocks.extend(self.security_scheme(requirement))

        blocks.extend(_bindings(server.bindings, hide=self.options.hide_bindings))
        return blocks

    def security_scheme(self, requirement) -> list[str]:
        scheme = self.doc.components.security_schemes.get(requirement.scheme_name)
        if scheme is None:
            return [f"- **Security:** `{requirement.scheme_name}`"]

        body = [f"**Type:** {scheme_pill(scheme.type.value)}", ""]
        for label, value in (("Name", scheme.parameter_name), ("In", scheme.location),
                             ("Scheme", scheme.scheme),
                             ("Bearer format", scheme.bearer_format),
                             ("OpenID Connect URL", scheme.open_id_connect_url)):
            if value:
                body.append(f"**{label}:** `{value}`")
        if scheme.description:
            if body[-1] != "":
                body.append("")
            body.append(_demote_headings(scheme.description.strip(), levels=2))
        if requirement.scopes:
            if body[-1] != "":
                body.append("")
            body.append("**Scopes:** " + ", ".join(f"`{s}`" for s in requirement.scopes))

        indented = "\n".join(("    " + line) if line else "" for line in body)
        return [f'!!! note ":material-security: Security: {requirement.scheme_name}"'
                f"\n{indented}"]

    # -- operations ---------------------------------------------------------

    def operations(self) -> list[str]:
        if not self.doc.operations:
            return []
        by_address: dict[str, Channel] = {c.address: c for c in self.doc.channels}

        blocks: list[str] = ["## Operations"]
        for operation in self.doc.operations:
            blocks.extend(self.operation(operation, by_address.get(operation.channel)))
        return blocks

    def operation(self, operation: Operation, channel: Channel | None) -> list[str]:
        line = action_pill(operation.action)
        if operation.channel:
            line += f" `{operation.channel}`"
        if operation.deprecated:
            line += " " + deprecated_pill()

        blocks = [
            _heading(3, operation.name, anchor=_anchor("operations", operation.name)),
            line,
        ]
        if operation.summary:
            blocks.append(operation.summary.strip())
        if operation.description:
            blocks.append(_demote_headings(operation.description.strip()))

        if channel is not None:
            blocks.extend(self.parameters_table(channel))

        blocks.extend(_ref_bullets("**Messages:**", operation.message_names, "messages"))
        blocks.extend(tag_pills(operation.tags))
        if not self.options.hide_traits:
            blocks.extend(_trait_names(operation.trait_names))
        blocks.extend(_bindings(operation.bindings, hide=self.options.hide_bindings))
        if channel is not None:
            # A channel has no section of its own, so what it binds is shown
            # beside each operation that runs on it.
            blocks.extend(_bindings(channel.bindings,
                                    hide=self.options.hide_bindings))
        return blocks

    @staticmethod
    def parameters_table(channel: Channel) -> list[str]:
        """
        The address placeholders, as one table.

        A placeholder has to be substituted for the address to resolve, so one
        named in the address is required.
        """
        if not channel.parameters:
            return []
        rows: list[str] = []
        for name, parameter in channel.parameters.items():
            schema = parameter.schema or Schema(types=("string",))

            name_html = _md_to_html(f"`{name}`", inline=True)
            if f"{{{name}}}" in channel.address:
                name_html += "<br>" + required_pill()

            described = describe(
                replace(schema, description=parameter.description)
                if parameter.description else schema
            )
            if parameter.location:
                described = (described + "\n" if described else "") \
                    + f"- Location: `{parameter.location}`"

            rows.append(
                f"<tr><td>{name_html}</td>"
                f"<td>{_md_to_html(format_type(schema), inline=True)}</td>"
                f"<td>{_md_to_html(described) if described else '&mdash;'}</td></tr>"
            )
        return ["**Parameters**", _html_table(PARAMETER_HEADERS, rows)]

    # -- messages -----------------------------------------------------------

    def all_messages(self) -> dict[str, Message]:
        """
        Every message the document describes, by name.

        A message may be declared under `components` or written inline on a
        channel, and an operation names it either way - so both have to be
        rendered, or a link lands nowhere.
        """
        messages = dict(self.doc.components.messages)
        for channel in self.doc.channels:
            for name, message in channel.messages.items():
                messages.setdefault(name, message)
        return messages

    def messages(self) -> list[str]:
        messages = self.all_messages()
        if not messages:
            return []
        blocks: list[str] = ["## Messages"]
        for name, message in messages.items():
            blocks.append(_heading(3, name, anchor=_anchor("messages", name)))
            blocks.extend(self.message(message, name))
        return blocks

    def message(self, message: Message, name: str) -> list[str]:
        blocks: list[str] = []
        if message.message_id:
            blocks.append(f"**Message ID:** `{message.message_id}`")
        if message.title and message.title != name:
            blocks.append(f"_{message.title}_")
        if message.summary:
            blocks.append(message.summary.strip())
        if message.description:
            blocks.append(_demote_headings(message.description.strip()))
        if message.content_type:
            blocks.append(
                f"**Content type:** {content_type_pill(message.content_type)}"
            )
        blocks.extend(tag_pills(message.tags))

        if message.correlation_id is not None:
            blocks.append(f"**Correlation id:** `{message.correlation_id.location}`")

        for label, schema in (("**Headers**", message.headers),
                              ("**Payload**", message.payload)):
            if schema is not None:
                blocks.append(label)
                blocks.extend(render_schema(
                    schema, hide_internal=self.options.hide_internal,
                    max_depth=self.options.schema_depth,
                ))

        if not self.options.hide_traits:
            blocks.extend(_trait_names(message.trait_names))
        blocks.extend(self.examples(message))
        blocks.extend(_bindings(message.bindings, hide=self.options.hide_bindings))
        return blocks

    @staticmethod
    def examples(message: Message) -> list[str]:
        if not message.examples:
            return []
        parts: list[str] = ["**Examples**"]
        for example in message.examples:
            label = example.name or example.summary
            if label:
                parts.append(f"_{label}_:")
            for payload in (example.headers, example.payload):
                if payload is None:
                    continue
                rendered = yaml.safe_dump(payload, sort_keys=False,
                                          default_flow_style=False).rstrip()
                parts.append(f"```yaml\n{rendered}\n```")
        return parts

    # -- schemas ------------------------------------------------------------

    def schemas(self) -> list[str]:
        schemas = self.doc.components.schemas
        if not schemas:
            return []
        blocks: list[str] = ["## Schemas"]
        for name, schema in schemas.items():
            blocks.append(_heading(3, name, anchor=_anchor("schemas", name)))
            blocks.extend(render_schema(
                schema, hide_internal=self.options.hide_internal,
                max_depth=self.options.schema_depth,
            ))
        return blocks

