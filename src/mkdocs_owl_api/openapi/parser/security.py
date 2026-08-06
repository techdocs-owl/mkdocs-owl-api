"""
Security schemes and requirements.

Requirement lists are spelled identically in every dialect. Scheme declarations
are not: 2.0 has three types and a flat flow, 3.x has five and a flows object.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...common.parse_report import Reporter
from ...common.parse_util import (
    extensions_of,
    is_mapping,
    kind_of,
    read_str,
    read_str_map,
    read_str_tuple,
)
from ..model import (
    OAuthFlow,
    OAuthFlows,
    ParameterLocation,
    SecurityRequirement,
    SecurityScheme,
    SecuritySchemeType,
)

#: 2.0 names three of the four flows differently.
_V2_FLOW_FIELDS = {
    "implicit": "implicit",
    "password": "password",
    "application": "client_credentials",
    "accessCode": "authorization_code",
}

_V3_FLOW_FIELDS = {
    "implicit": "implicit",
    "password": "password",
    "clientCredentials": "client_credentials",
    "authorizationCode": "authorization_code",
}


def read_requirements(
    raw: Any, report: Reporter,
) -> tuple[tuple[SecurityRequirement, ...], ...]:
    """
    A `security` list.

    The outer list is alternatives; the keys of each entry must all hold at
    once. The model's nesting carries that, so nothing is flattened away.
    """
    if not isinstance(raw, list):
        report.warn(f"expected an array, found {kind_of(raw)}")
        return ()

    alternatives: list[tuple[SecurityRequirement, ...]] = []
    for index, entry in enumerate(raw):
        at = report.at(index)
        if not is_mapping(entry):
            at.warn(f"expected an object, found {kind_of(entry)}")
            continue
        required = tuple(
            SecurityRequirement(
                scheme_name=str(name), scopes=read_str_tuple(entry, str(name), at),
            )
            for name in entry
        )
        if required:
            alternatives.append(required)
    return tuple(alternatives)


def _read_flow(raw: Mapping[str, Any], report: Reporter) -> OAuthFlow:
    return OAuthFlow(
        authorization_url=read_str(raw, "authorizationUrl", report),
        token_url=read_str(raw, "tokenUrl", report),
        refresh_url=read_str(raw, "refreshUrl", report),
        scopes=read_str_map(raw, "scopes", report),
    )


def read_v3_scheme(
    name: str, raw: Mapping[str, Any], report: Reporter,
) -> SecurityScheme | None:
    declared = read_str(raw, "type", report)
    try:
        scheme_type = SecuritySchemeType(declared)
    except ValueError:
        report.warn(f"unknown security scheme type `{declared}`")
        return None

    flows = None
    raw_flows = raw.get("flows")
    if is_mapping(raw_flows):
        built = {
            field: _read_flow(raw_flows[key], report.at("flows", key))
            for key, field in _V3_FLOW_FIELDS.items()
            if is_mapping(raw_flows.get(key))
        }
        if built:
            flows = OAuthFlows(**built)
    elif raw_flows is not None:
        report.at("flows").warn(f"expected an object, found {kind_of(raw_flows)}")

    return SecurityScheme(
        name=name,
        type=scheme_type,
        description=read_str(raw, "description", report),
        parameter_name=read_str(raw, "name", report),
        location=_read_location(raw, report),
        scheme=read_str(raw, "scheme", report),
        bearer_format=read_str(raw, "bearerFormat", report),
        flows=flows,
        open_id_connect_url=read_str(raw, "openIdConnectUrl", report),
        extensions=extensions_of(raw),
    )


def read_v2_scheme(
    name: str, raw: Mapping[str, Any], report: Reporter,
) -> SecurityScheme | None:
    """
    A `securityDefinitions` entry.

    `basic` is the 2.0 spelling of what 3.x calls an `http` scheme carrying
    `scheme: basic`, and the single `flow` names one of the four flows.
    """
    declared = read_str(raw, "type", report)

    if declared == "basic":
        return SecurityScheme(
            name=name,
            type=SecuritySchemeType.HTTP,
            description=read_str(raw, "description", report),
            scheme="basic",
            extensions=extensions_of(raw),
        )

    if declared == "apiKey":
        return SecurityScheme(
            name=name,
            type=SecuritySchemeType.API_KEY,
            description=read_str(raw, "description", report),
            parameter_name=read_str(raw, "name", report),
            location=_read_location(raw, report),
            extensions=extensions_of(raw),
        )

    if declared == "oauth2":
        flows = None
        flow_name = read_str(raw, "flow", report)
        field = _V2_FLOW_FIELDS.get(flow_name or "")
        if field is None:
            report.at("flow").warn(f"unknown OAuth flow `{flow_name}`")
        else:
            flows = OAuthFlows(**{field: _read_flow(raw, report)})
        return SecurityScheme(
            name=name,
            type=SecuritySchemeType.OAUTH2,
            description=read_str(raw, "description", report),
            flows=flows,
            extensions=extensions_of(raw),
        )

    report.warn(f"unknown security scheme type `{declared}`")
    return None


def _read_location(raw: Mapping[str, Any], report: Reporter) -> ParameterLocation | None:
    declared = read_str(raw, "in", report)
    if declared is None:
        return None
    try:
        return ParameterLocation(declared)
    except ValueError:
        report.at("in").warn(f"unknown location `{declared}`")
        return None
