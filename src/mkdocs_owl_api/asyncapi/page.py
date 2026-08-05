"""
AsyncAPI 2.x/3.0 page builder.
"""

from __future__ import annotations

from ..common.base import PageBuilder
from ..common.builders import SchemasBuilder
from .builders import (
    DefaultContentTypeBuilder,
    MessagesBuilder,
    OperationsBuilder,
    ParametersBuilder,
    ServersBuilder,
    TraitsBuilder,
)


class AsyncApiPageBuilder(PageBuilder):
    """
    Section order for an AsyncAPI reference page.
    """

    def sections(self) -> list:
        ctx = self.ctx
        return [
            DefaultContentTypeBuilder(ctx),
            ServersBuilder(ctx),
            OperationsBuilder(ctx),
            MessagesBuilder(ctx),
            SchemasBuilder(ctx),
            ParametersBuilder(ctx),
            TraitsBuilder(ctx, container="messageTraits", heading="Message traits"),
            TraitsBuilder(ctx, container="operationTraits", heading="Operation traits"),
        ]
