"""
AsyncAPI 2.x/3.0 page builder.
"""

from __future__ import annotations

from ..common.base import PageBuilder
from ..common.builders import (
    AttachmentsBuilder,
    InfoDescriptionBuilder,
    InfoExtrasBuilder,
    SchemasBuilder,
)
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

    The base class contributes the title/intro/version preamble; everything
    below is this flavour's, which is the whole point of the subclass owning
    assembly rather than a caller wiring parts in from outside.
    """

    spec_type = "AsyncAPI"

    def sections(self) -> list:
        ctx = self.ctx
        return [
            AttachmentsBuilder(ctx, self.spec_type),
            InfoExtrasBuilder(ctx),
            DefaultContentTypeBuilder(ctx),
            InfoDescriptionBuilder(ctx),
            ServersBuilder(ctx),
            OperationsBuilder(ctx),
            MessagesBuilder(ctx),
            SchemasBuilder(ctx),
            ParametersBuilder(ctx),
            TraitsBuilder(ctx, container="messageTraits", heading="Message traits"),
            TraitsBuilder(ctx, container="operationTraits", heading="Operation traits"),
        ]
