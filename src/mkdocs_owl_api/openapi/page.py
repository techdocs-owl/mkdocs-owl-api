"""
OpenAPI 3.x page builder.
"""

from __future__ import annotations

from ..common.base import PageBuilder
from ..common.builders import SchemasBuilder
from .builders import EndpointsBuilder, ServersBuilder


class OpenApiPageBuilder(PageBuilder):
    """
    Section order for an OpenAPI reference page.
    """

    def sections(self) -> list:
        ctx = self.ctx
        return [
            ServersBuilder(ctx),
            EndpointsBuilder(ctx),
            SchemasBuilder(ctx),
        ]
