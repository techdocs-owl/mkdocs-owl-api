"""
AsyncAPI document model.

One shape for both dialects. The restructuring that makes that possible happens
on the way in: 2.x states operations as `publish`/`subscribe` on a channel and
3.0 states them as a top-level map with an `action`, and the two vocabularies
mean opposite things - `publish` describes what a *client* does, `send` and
`receive` describe what the *application* does. Everything here is the
application's point of view.

Scope is the part of the specification this plugin covers. `reply`, `$id`-based
schema registries and non-JSON-Schema payload formats are absent for now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..doc_types import ApiDoc, ExternalDocs, Tag
from ..jsonschema.schema_types import Schema


class AsyncApiDialect(Enum):
    """
    Source dialect, to the granularity that matters.

    The 2.x line differs from 3.0 in where operations, messages and server
    addresses live; within 2.x those are the same.
    """

    V2 = "2"
    V3 = "3"


class OperationAction(Enum):
    """
    What the application does, which is what 3.0 states directly.

    A 2.x `subscribe` operation is one the application sends on, and a 2.x
    `publish` operation is one it receives on.
    """

    SEND = "send"
    RECEIVE = "receive"


class SecuritySchemeType(Enum):
    """Kind of security scheme. Wider than the HTTP-only set."""

    USER_PASSWORD = "userPassword"
    API_KEY = "apiKey"
    X509 = "X509"
    SYMMETRIC_ENCRYPTION = "symmetricEncryption"
    ASYMMETRIC_ENCRYPTION = "asymmetricEncryption"
    HTTP_API_KEY = "httpApiKey"
    HTTP = "http"
    OAUTH2 = "oauth2"
    OPEN_ID_CONNECT = "openIdConnect"
    PLAIN = "plain"
    SCRAM_SHA256 = "scramSha256"
    SCRAM_SHA512 = "scramSha512"
    GSSAPI = "gssapi"


@dataclass(frozen=True)
class SecurityRequirement:
    """One scheme a server or operation requires, with the scopes it needs."""

    scheme_name: str = ""
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecurityScheme:
    """A declared security scheme."""

    name: str = ""
    type: SecuritySchemeType = SecuritySchemeType.USER_PASSWORD
    description: str | None = None
    parameter_name: str | None = None
    location: str | None = None
    scheme: str | None = None
    bearer_format: str | None = None
    open_id_connect_url: str | None = None
    scopes: dict[str, str] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ServerVariable:
    """A `{placeholder}` in a server address."""

    default: str = ""
    enum: tuple[str, ...] = ()
    description: str | None = None
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class Server:
    """
    One server the application is reachable at.

    `host` and `pathname` are stated separately, which is 3.0's form; a 2.x
    `url` is split onto them so both dialects describe an address the same way.
    """

    name: str = ""
    host: str = ""
    protocol: str | None = None
    protocol_version: str | None = None
    pathname: str | None = None
    title: str | None = None
    summary: str | None = None
    description: str | None = None
    variables: dict[str, ServerVariable] = field(default_factory=dict)
    tags: tuple[Tag, ...] = ()
    security: tuple[tuple[SecurityRequirement, ...], ...] = ()
    bindings: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)

    @property
    def url(self) -> str:
        """The address as one string, for somewhere that wants it that way."""
        scheme = f"{self.protocol}://" if self.protocol else ""
        return f"{scheme}{self.host}{self.pathname or ''}"


@dataclass(frozen=True)
class CorrelationId:
    """Where in a message the correlation value is found."""

    location: str = ""
    description: str | None = None


@dataclass(frozen=True)
class MessageExample:
    """A worked example of a message."""

    name: str | None = None
    summary: str | None = None
    headers: Any = None
    payload: Any = None


@dataclass(frozen=True)
class Message:
    """
    One message, with any traits it declares already folded in.

    The spec says a trait's fields are merged into the message; `trait_names`
    keeps what was applied so it can still be named.
    """

    name: str = ""
    message_id: str | None = None
    title: str | None = None
    summary: str | None = None
    description: str | None = None
    content_type: str | None = None
    headers: Schema | None = None
    payload: Schema | None = None
    correlation_id: CorrelationId | None = None
    tags: tuple[Tag, ...] = ()
    external_docs: ExternalDocs | None = None
    examples: tuple[MessageExample, ...] = ()
    bindings: dict[str, Any] = field(default_factory=dict)
    trait_names: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Parameter:
    """
    A `{placeholder}` in a channel address.

    The value's shape - its type, and any allowed values, default or examples -
    is one `schema`, wherever the source stated those facts.
    """

    name: str = ""
    description: str | None = None
    #: Runtime expression saying where the value comes from.
    location: str | None = None
    schema: Schema | None = None


@dataclass(frozen=True)
class Channel:
    """
    One address messages flow over.

    2.x keys channels by their address; 3.0 keys them by a name and states the
    address separately. Both are recorded.
    """

    name: str = ""
    address: str = ""
    title: str | None = None
    summary: str | None = None
    description: str | None = None
    #: Names of the servers this channel is available on; empty means all.
    servers: tuple[str, ...] = ()
    parameters: dict[str, Parameter] = field(default_factory=dict)
    #: Messages carried, by name.
    messages: dict[str, Message] = field(default_factory=dict)
    bindings: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Operation:
    """
    One thing the application does on a channel.

    Traits are folded in, as for a message, with `trait_names` keeping what was
    applied.
    """

    name: str = ""
    action: OperationAction = OperationAction.RECEIVE
    #: The address of the channel this runs on.
    channel: str = ""
    title: str | None = None
    summary: str | None = None
    description: str | None = None
    deprecated: bool = False
    tags: tuple[Tag, ...] = ()
    external_docs: ExternalDocs | None = None
    security: tuple[tuple[SecurityRequirement, ...], ...] = ()
    #: Names of the messages this operation applies to.
    message_names: tuple[str, ...] = ()
    bindings: dict[str, Any] = field(default_factory=dict)
    trait_names: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Components:
    """Reusable objects by name."""

    schemas: dict[str, Schema] = field(default_factory=dict)
    messages: dict[str, Message] = field(default_factory=dict)
    security_schemes: dict[str, SecurityScheme] = field(default_factory=dict)
    parameters: dict[str, Parameter] = field(default_factory=dict)
    correlation_ids: dict[str, CorrelationId] = field(default_factory=dict)
    #: Traits are shaped like the thing they apply to, so they are modelled as
    #: one, with only the fields the trait stated filled in.
    message_traits: dict[str, Message] = field(default_factory=dict)
    operation_traits: dict[str, Operation] = field(default_factory=dict)


@dataclass(frozen=True)
class AsyncApiDoc(ApiDoc):
    """A described event-driven API."""

    dialect: AsyncApiDialect = AsyncApiDialect.V3
    default_content_type: str | None = None
    servers: tuple[Server, ...] = ()
    channels: tuple[Channel, ...] = ()
    operations: tuple[Operation, ...] = ()
    components: Components = field(default_factory=Components)

    @property
    def spec_version_key(self) -> str:
        return "asyncapi"
