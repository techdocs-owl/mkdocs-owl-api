"""
OpenAPI document model.

One dialect-neutral shape. Nothing here records which version the description
came from, except `ApiDoc.dialect` and `ApiDoc.spec_version`, which exist so a
page can print the source version.

Scope is the part of the specification this plugin covers: `Link`, `Callback`,
`webhooks`, `xml` and `pathItems` components are absent by design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..common.doc_model import ExternalDocs, Info, Tag
from ..common.schema_model import UNSET, Schema


class OpenApiDialect(Enum):
    """
    Source dialect, to the granularity that matters.

    3.0 and 3.1 are separate members because they differ in more than a patch
    number: 3.1 uses JSON Schema 2020-12, allows annotations beside `$ref`, and
    adds `info.summary` and SPDX `license.identifier`.
    """

    V2_0 = "2.0"
    V3_0 = "3.0"
    V3_1 = "3.1"


class HttpMethod(Enum):
    """The methods a path may declare."""

    GET = "get"
    PUT = "put"
    POST = "post"
    DELETE = "delete"
    OPTIONS = "options"
    HEAD = "head"
    PATCH = "patch"
    TRACE = "trace"


class ParameterLocation(Enum):
    """Where a parameter is carried. A body is a `RequestBody`, not a location."""

    QUERY = "query"
    HEADER = "header"
    PATH = "path"
    COOKIE = "cookie"


class SecuritySchemeType(Enum):
    """Kind of security scheme."""

    API_KEY = "apiKey"
    HTTP = "http"
    OAUTH2 = "oauth2"
    OPEN_ID_CONNECT = "openIdConnect"
    MUTUAL_TLS = "mutualTLS"


@dataclass(frozen=True)
class ServerVariable:
    """A `{placeholder}` in a server URL."""

    default: str = ""
    enum: tuple[str, ...] = ()
    description: str | None = None


@dataclass(frozen=True)
class Server:
    """One server the API is reachable at."""

    url: str = ""
    description: str | None = None
    variables: dict[str, ServerVariable] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Example:
    """A named example. `value` and `external_value` are mutually exclusive."""

    summary: str | None = None
    description: str | None = None
    value: Any = UNSET
    external_value: str | None = None


@dataclass(frozen=True)
class Encoding:
    """Serialisation of one property of a form-encoded or multipart body."""

    content_type: str | None = None
    headers: dict[str, Header] = field(default_factory=dict)
    style: str | None = None
    explode: bool | None = None
    allow_reserved: bool = False


@dataclass(frozen=True)
class MediaType:
    """The schema and examples for one media type of a `content` map."""

    schema: Schema | None = None
    example: Any = UNSET
    examples: dict[str, Example] = field(default_factory=dict)
    encoding: dict[str, Encoding] = field(default_factory=dict)


@dataclass(frozen=True)
class Parameter:
    """One parameter of an operation or path."""

    name: str = ""
    location: ParameterLocation = ParameterLocation.QUERY
    description: str | None = None
    required: bool = False
    deprecated: bool = False
    allow_empty_value: bool = False
    #: How the value is serialised into the request.
    style: str | None = None
    explode: bool | None = None
    schema: Schema | None = None
    example: Any = UNSET
    examples: dict[str, Example] = field(default_factory=dict)
    #: The `content` form of a parameter, mutually exclusive with `schema`.
    content: dict[str, MediaType] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Header:
    """
    A response or encoding header.

    A `Parameter` without `name` or `location`, kept separate so neither can be
    read where it has no meaning - the name is the containing map key.
    """

    description: str | None = None
    required: bool = False
    deprecated: bool = False
    style: str | None = None
    explode: bool | None = None
    schema: Schema | None = None
    example: Any = UNSET
    examples: dict[str, Example] = field(default_factory=dict)
    content: dict[str, MediaType] = field(default_factory=dict)


@dataclass(frozen=True)
class RequestBody:
    """An operation's request body, one entry per media type."""

    description: str | None = None
    required: bool = False
    content: dict[str, MediaType] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Response:
    """One possible response to an operation."""

    #: Source key verbatim, including `default` and wildcards such as `2XX`.
    status_code: str = ""
    description: str | None = None
    headers: dict[str, Header] = field(default_factory=dict)
    content: dict[str, MediaType] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SecurityRequirement:
    """
    One scheme an operation requires, with the scopes it needs.

    `scopes` is empty for every type but `oauth2` and `openIdConnect`.
    """

    scheme_name: str = ""
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class OAuthFlow:
    """
    One OAuth flow.

    Which URLs apply depends on the flow; the `OAuthFlows` field holding this
    says which flow it is.
    """

    authorization_url: str | None = None
    token_url: str | None = None
    refresh_url: str | None = None
    #: Scope name -> description.
    scopes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OAuthFlows:
    """The flows an `oauth2` scheme supports."""

    implicit: OAuthFlow | None = None
    password: OAuthFlow | None = None
    client_credentials: OAuthFlow | None = None
    authorization_code: OAuthFlow | None = None


@dataclass(frozen=True)
class SecurityScheme:
    """
    A declared security scheme.

    `parameter_name` and `location` apply to `apiKey`, `scheme` and
    `bearer_format` to `http`, `flows` to `oauth2`, and `open_id_connect_url` to
    `openIdConnect`.
    """

    name: str = ""
    type: SecuritySchemeType = SecuritySchemeType.API_KEY
    description: str | None = None
    parameter_name: str | None = None
    location: ParameterLocation | None = None
    scheme: str | None = None
    bearer_format: str | None = None
    flows: OAuthFlows | None = None
    open_id_connect_url: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Operation:
    """One method on one path."""

    method: HttpMethod = HttpMethod.GET
    #: Denormalised from the containing `PathItem`, so an operation identifies
    #: itself without its container.
    path: str = ""
    operation_id: str | None = None
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    deprecated: bool = False
    #: Path-level and operation-level parameters merged, the operation's winning
    #: on a `(name, location)` collision.
    parameters: tuple[Parameter, ...] = ()
    request_body: RequestBody | None = None
    responses: tuple[Response, ...] = ()
    #: Alternatives, any one of which suffices; each inner tuple must be
    #: satisfied in full. `None` inherits `ApiDoc.security`, whereas an empty
    #: tuple opts out of it.
    security: tuple[tuple[SecurityRequirement, ...], ...] | None = None
    servers: tuple[Server, ...] = ()
    external_docs: ExternalDocs | None = None
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PathItem:
    """One path template and the operations on it."""

    path: str = ""
    summary: str | None = None
    description: str | None = None
    operations: tuple[Operation, ...] = ()
    #: As declared. `Operation.parameters` holds the merged view.
    parameters: tuple[Parameter, ...] = ()
    servers: tuple[Server, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Components:
    """Reusable objects by name. What a schema's `$ref` resolves against."""

    schemas: dict[str, Schema] = field(default_factory=dict)
    responses: dict[str, Response] = field(default_factory=dict)
    parameters: dict[str, Parameter] = field(default_factory=dict)
    examples: dict[str, Example] = field(default_factory=dict)
    request_bodies: dict[str, RequestBody] = field(default_factory=dict)
    headers: dict[str, Header] = field(default_factory=dict)
    security_schemes: dict[str, SecurityScheme] = field(default_factory=dict)


@dataclass(frozen=True)
class ApiDoc:
    """
    A described API.

    `dialect` and `spec_version` are the one concession to where the description
    came from: they record the version the source declared. Branching on them
    for anything else reintroduces the version coupling this model removes.
    """

    dialect: OpenApiDialect = OpenApiDialect.V3_1
    #: Verbatim root value, e.g. `3.0.2` - the enum carries only the minor.
    spec_version: str = ""
    info: Info = field(default_factory=Info)
    servers: tuple[Server, ...] = ()
    tags: tuple[Tag, ...] = ()
    paths: tuple[PathItem, ...] = ()
    components: Components = field(default_factory=Components)
    #: Document-wide default; see `Operation.security` for the override rules.
    security: tuple[tuple[SecurityRequirement, ...], ...] = ()
    external_docs: ExternalDocs | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    @property
    def spec_version_key(self) -> str:
        """The root key the source used: `swagger` for 2.0, else `openapi`."""
        return "swagger" if self.dialect is OpenApiDialect.V2_0 else "openapi"
