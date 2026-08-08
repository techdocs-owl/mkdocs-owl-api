"""
The four places 2.x and 3.0 describe the same thing differently.

Servers state their address one way or the other; channels are keyed by address
or by name; operations hang off a channel or sit in a map of their own; and the
words for what an operation does are opposite. Everything else is shared
traversal in `document.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from ...common.doc_parser import read_external_docs
from ...common.parse_refs import RefResolver
from ...common.parse_report import Reporter
from ...common.parse_util import (
    extensions_of,
    is_mapping,
    read_bool,
    read_mapping,
    read_str,
    read_str_tuple,
)
from ...jsonschema.schema_parser import read_schema
from ..model import (
    AsyncApiDialect,
    Channel,
    Components,
    Message,
    Operation,
    OperationAction,
    Server,
)
from .document import (
    apply_traits,
    name_of,
    read_bindings,
    read_correlation_id,
    read_message,
    read_parameter,
    read_parameters,
    read_security_requirements,
    read_security_scheme,
    read_server_variables,
    read_tags,
)

#: What a 2.x channel operation means from the application's side. A client
#: publishes *to* the application, so the application receives.
_V2_ACTIONS = {"publish": OperationAction.RECEIVE, "subscribe": OperationAction.SEND}


class Dialect(Protocol):
    version: AsyncApiDialect

    def servers(self, report: Reporter) -> tuple[Server, ...]: ...
    def channels(self, report: Reporter) -> tuple[Channel, ...]: ...
    def operations(
        self, channels: tuple[Channel, ...], report: Reporter,
    ) -> tuple[Operation, ...]: ...
    def components(self, report: Reporter) -> Components: ...


def _split_url(url: str, protocol: str | None) -> tuple[str, str | None, str | None]:
    """A 2.x `url` as the host, path and protocol that 3.0 states separately."""
    rest = url
    if "://" in rest:
        scheme, _, rest = rest.partition("://")
        protocol = protocol or scheme
    host, slash, path = rest.partition("/")
    return host, (slash + path) if slash else None, protocol


class _Common:
    """Reading that differs only in where the objects are found."""

    def __init__(self, root: Mapping[str, Any], resolver: RefResolver):
        self._root = root
        self._resolver = resolver

    def components(self, report: Reporter) -> Components:
        raw = read_mapping(self._root, "components", report) or {}
        at = report.at("components")
        resolver = self._resolver

        def each(key: str, reader):
            node = read_mapping(raw, key, at) or {}
            built = {}
            for name, value in node.items():
                item = reader(str(name), value, at.at(key, name))
                if item is not None:
                    built[str(name)] = item
            return built

        return Components(
            schemas=each("schemas", lambda n, v, w: read_schema(v, w)),
            messages=each("messages", lambda n, v, w: read_message(n, v, resolver, w)),
            security_schemes=each("securitySchemes",
                                  lambda n, v, w: read_security_scheme(n, v, w)),
            parameters=each("parameters",
                            lambda n, v, w: read_parameter(n, v, resolver, w)),
            correlation_ids=each("correlationIds",
                                 lambda n, v, w: read_correlation_id(v, resolver, w)),
            message_traits=each("messageTraits",
                                lambda n, v, w: read_message(n, v, resolver, w)),
            operation_traits=each("operationTraits",
                                  lambda n, v, w: self._trait_operation(n, v, w)),
        )

    def _trait_operation(self, name: str, raw: Any, report: Reporter) -> Operation | None:
        if not is_mapping(raw):
            report.warn("expected an object")
            return None
        return Operation(
            name=name,
            summary=read_str(raw, "summary", report),
            description=read_str(raw, "description", report),
            tags=read_tags(raw.get("tags"), report.at("tags")),
            external_docs=read_external_docs(
                raw.get("externalDocs"), report.at("externalDocs"),
            ),
            bindings=read_bindings(raw, report),
            extensions=extensions_of(raw),
        )


class V3Dialect(_Common):
    """AsyncAPI 3.0: channels keyed by name, operations in a map of their own."""

    version = AsyncApiDialect.V3

    def servers(self, report: Reporter) -> tuple[Server, ...]:
        built: list[Server] = []
        for name, raw in (read_mapping(self._root, "servers", report) or {}).items():
            at = report.at("servers", name)
            raw = self._resolver.resolve(raw, at)
            if not is_mapping(raw):
                continue
            built.append(Server(
                name=str(name),
                host=read_str(raw, "host", at) or "",
                protocol=read_str(raw, "protocol", at),
                protocol_version=read_str(raw, "protocolVersion", at),
                pathname=read_str(raw, "pathname", at),
                title=read_str(raw, "title", at),
                summary=read_str(raw, "summary", at),
                description=read_str(raw, "description", at),
                variables=read_server_variables(raw, self._resolver, at),
                tags=read_tags(raw.get("tags"), at.at("tags")),
                security=read_security_requirements(
                    raw.get("security"), self._resolver, at.at("security"),
                ),
                bindings=read_bindings(raw, at),
                extensions=extensions_of(raw),
            ))
        return tuple(built)

    def channels(self, report: Reporter) -> tuple[Channel, ...]:
        built: list[Channel] = []
        for name, raw in (read_mapping(self._root, "channels", report) or {}).items():
            at = report.at("channels", name)
            raw = self._resolver.resolve(raw, at)
            if not is_mapping(raw):
                continue
            messages: dict[str, Message] = {}
            for message_name, value in (read_mapping(raw, "messages", at) or {}).items():
                message = read_message(str(message_name), value, self._resolver,
                                       at.at("messages", message_name))
                if message is not None:
                    messages[str(message_name)] = message
            built.append(Channel(
                name=str(name),
                address=read_str(raw, "address", at) or str(name),
                title=read_str(raw, "title", at),
                summary=read_str(raw, "summary", at),
                description=read_str(raw, "description", at),
                servers=tuple(
                    name_of(entry["$ref"]) for entry in raw.get("servers") or []
                    if is_mapping(entry) and isinstance(entry.get("$ref"), str)
                ),
                parameters=read_parameters(raw, self._resolver, at),
                messages=messages,
                bindings=read_bindings(raw, at),
                extensions=extensions_of(raw),
            ))
        return tuple(built)

    def operations(
        self, channels: tuple[Channel, ...], report: Reporter,
    ) -> tuple[Operation, ...]:
        by_name = {channel.name: channel for channel in channels}
        built: list[Operation] = []

        for name, raw in (read_mapping(self._root, "operations", report) or {}).items():
            at = report.at("operations", name)
            if not is_mapping(raw):
                at.warn("expected an object")
                continue
            merged, trait_names = apply_traits(raw, self._resolver, at)

            declared = read_str(merged, "action", at)
            try:
                action = OperationAction(declared)
            except ValueError:
                at.at("action").warn(f"unknown action `{declared}`")
                continue

            channel_ref = merged.get("channel")
            channel_name = (
                name_of(channel_ref["$ref"])
                if is_mapping(channel_ref) and isinstance(channel_ref.get("$ref"), str)
                else ""
            )
            channel = by_name.get(channel_name)

            built.append(Operation(
                name=str(name),
                action=action,
                channel=channel.address if channel else channel_name,
                title=read_str(merged, "title", at),
                summary=read_str(merged, "summary", at),
                description=read_str(merged, "description", at),
                deprecated=bool(read_bool(merged, "deprecated", at)),
                tags=read_tags(merged.get("tags"), at.at("tags")),
                external_docs=read_external_docs(
                    merged.get("externalDocs"), at.at("externalDocs"),
                ),
                security=read_security_requirements(
                    merged.get("security"), self._resolver, at.at("security"),
                ),
                message_names=tuple(
                    name_of(entry["$ref"]) for entry in merged.get("messages") or []
                    if is_mapping(entry) and isinstance(entry.get("$ref"), str)
                ),
                bindings=read_bindings(merged, at),
                trait_names=trait_names,
                extensions=extensions_of(merged),
            ))
        return tuple(built)


class V2Dialect(_Common):
    """AsyncAPI 2.x: channels keyed by address, operations hanging off them."""

    version = AsyncApiDialect.V2

    def servers(self, report: Reporter) -> tuple[Server, ...]:
        built: list[Server] = []
        for name, raw in (read_mapping(self._root, "servers", report) or {}).items():
            at = report.at("servers", name)
            raw = self._resolver.resolve(raw, at)
            if not is_mapping(raw):
                continue
            protocol = read_str(raw, "protocol", at)
            host, pathname, protocol = _split_url(read_str(raw, "url", at) or "", protocol)
            built.append(Server(
                name=str(name),
                host=host,
                protocol=protocol,
                protocol_version=read_str(raw, "protocolVersion", at),
                pathname=pathname,
                description=read_str(raw, "description", at),
                variables=read_server_variables(raw, self._resolver, at),
                tags=read_tags(raw.get("tags"), at.at("tags")),
                security=read_security_requirements(
                    raw.get("security"), self._resolver, at.at("security"),
                ),
                bindings=read_bindings(raw, at),
                extensions=extensions_of(raw),
            ))
        return tuple(built)

    def _messages_of(
        self, operation: Any, fallback: str, at: Reporter,
    ) -> dict[str, Message]:
        """
        The messages one 2.x operation carries.

        A `message` is either one message or a `oneOf` list of them, and either
        form may be a reference.
        """
        if not is_mapping(operation):
            return {}
        declared = operation.get("message")
        if not is_mapping(declared):
            return {}
        members = declared.get("oneOf")
        members = members if isinstance(members, list) else [declared]

        messages: dict[str, Message] = {}
        for index, member in enumerate(members):
            where = at.at("message", index)
            resolved = self._resolver.resolve(member, where)
            if not is_mapping(resolved):
                continue
            name = (
                (name_of(member["$ref"])
                 if is_mapping(member) and isinstance(member.get("$ref"), str) else None)
                or read_str(resolved, "name", where)
                or read_str(resolved, "messageId", where)
                or read_str(resolved, "title", where)
                or f"{fallback}-message"
            )
            message = read_message(str(name), resolved, self._resolver, where)
            if message is not None:
                messages[str(name)] = message
        return messages

    def channels(self, report: Reporter) -> tuple[Channel, ...]:
        built: list[Channel] = []
        for address, raw in (read_mapping(self._root, "channels", report) or {}).items():
            at = report.at("channels", address)
            raw = self._resolver.resolve(raw, at)
            if not is_mapping(raw):
                continue
            built.append(Channel(
                name=str(address),
                address=str(address),
                description=read_str(raw, "description", at),
                servers=read_str_tuple(raw, "servers", at),
                parameters=read_parameters(raw, self._resolver, at),
                messages={
                    name: message
                    for action in ("publish", "subscribe")
                    for name, message in self._messages_of(
                        raw.get(action), action, at.at(action)).items()
                },
                bindings=read_bindings(raw, at),
                extensions=extensions_of(raw),
            ))
        return tuple(built)

    def operations(
        self, channels: tuple[Channel, ...], report: Reporter,
    ) -> tuple[Operation, ...]:
        raw_channels = read_mapping(self._root, "channels", report) or {}
        built: list[Operation] = []

        for address, raw in raw_channels.items():
            raw = self._resolver.resolve(raw, report.at("channels", address))
            if not is_mapping(raw):
                continue
            for source_action, action in _V2_ACTIONS.items():
                operation = raw.get(source_action)
                if not is_mapping(operation):
                    continue
                at = report.at("channels", address, source_action)
                merged, trait_names = apply_traits(operation, self._resolver, at)

                built.append(Operation(
                    name=(read_str(merged, "operationId", at)
                          or f"{source_action} {address}"),
                    action=action,
                    channel=str(address),
                    summary=read_str(merged, "summary", at),
                    description=read_str(merged, "description", at),
                    deprecated=bool(read_bool(merged, "deprecated", at)),
                    tags=read_tags(merged.get("tags"), at.at("tags")),
                    external_docs=read_external_docs(
                        merged.get("externalDocs"), at.at("externalDocs"),
                    ),
                    security=read_security_requirements(
                        merged.get("security"), self._resolver, at.at("security"),
                    ),
                    message_names=tuple(self._messages_of(
                        operation, source_action, at)),
                    bindings=read_bindings(merged, at),
                    trait_names=trait_names,
                    extensions=extensions_of(merged),
                ))
        return tuple(built)
