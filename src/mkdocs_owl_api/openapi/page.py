"""
OpenAPI 3.x page builder.
"""

from __future__ import annotations

from ..common.base import PageBuilder
from ..common.builders import (
    AttachmentsBuilder,
    InfoDescriptionBuilder,
    SchemasBuilder,
)
from .builders import EndpointsBuilder, ServersBuilder


class OpenApiPageBuilder(PageBuilder):
    """
    Section order for an OpenAPI reference page.

    `InfoExtrasBuilder` is deliberately absent: OpenAPI pages drop
    `info.license` / `contact` / `externalDocs` today (`code-improvements.md`
    §2), and adding them is a behaviour change with its own commit.
    """

    spec_type = "OpenAPI"

    def sections(self) -> list:
        ctx = self.ctx
        return [
            AttachmentsBuilder(ctx, self.spec_type),
            InfoDescriptionBuilder(ctx),
            ServersBuilder(ctx),
            EndpointsBuilder(ctx),
            SchemasBuilder(ctx),
        ]
