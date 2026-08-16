from __future__ import annotations

import unittest

from mkdocs_owl_api.asyncapi import Renderer, parse_document
from mkdocs_owl_api.common.render import RenderContext
from mkdocs_owl_api.options import PageOptions

from ..fixtures import ASYNCAPI_V2, ASYNCAPI_V3


def render(spec, **options):
    opts = PageOptions(type="asyncapi", spec="spec.yml", **options)
    return Renderer(parse_document(spec).doc, RenderContext(options=opts)).render()


class TestPage(unittest.TestCase):
    def test_both_dialects_render_the_same_page(self):
        strip = lambda page: "\n".join(
            line for line in page.split("\n") if "**Specification:**" not in line
        )
        self.assertEqual(strip(render(ASYNCAPI_V2)), strip(render(ASYNCAPI_V3)))

    def test_specification_line_names_the_source(self):
        self.assertIn("`asyncapi 2.6.0`", render(ASYNCAPI_V2))
        self.assertIn("`asyncapi 3.0.0`", render(ASYNCAPI_V3))

    def test_sections(self):
        page = render(ASYNCAPI_V3)
        for expected in ("# Streetlights", "**Default content type:**", "## Servers",
                         "### production",
                         ":material-link-variant: `mqtt://test.mosquitto.org:8883`",
                         "## Operations", "### receiveLightMeasurement",
                         "## Messages", "### LightMeasured", "## Schemas"):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)

    def test_actions_read_from_the_application_side(self):
        # A 2.x `publish` is something the application receives, so both
        # documents print the same word for the same operation.
        for spec in (ASYNCAPI_V2, ASYNCAPI_V3):
            with self.subTest(version=spec["asyncapi"]):
                block = render(spec).split("### receiveLightMeasurement")[1]
                self.assertIn(">receive<", block.split("###")[0])

    def test_action_and_address_share_a_line(self):
        for spec in (ASYNCAPI_V2, ASYNCAPI_V3):
            with self.subTest(version=spec["asyncapi"]):
                self.assertIn(">receive</span> `light/{streetlightId}/measured`", render(spec))

    def test_parameters_render_as_a_table(self):
        block = render(ASYNCAPI_V3).split("### receiveLightMeasurement")[1]
        self.assertIn("**Parameters**", block)
        self.assertIn("<th>Name</th><th>Type</th><th>Description</th>", block)
        self.assertIn("<code>streetlightId</code>", block)

    def test_a_parameter_is_typed_and_required(self):
        # Both facts come from the specification: an address placeholder holds a
        # string, and has to be substituted for the address to resolve.
        for spec in (ASYNCAPI_V2, ASYNCAPI_V3):
            with self.subTest(version=spec["asyncapi"]):
                row = render(spec).split("<code>streetlightId</code>")[1]
                self.assertIn(">required</span>", row.split("</tr>")[0])
                self.assertIn("<td>string</td>", row.split("</tr>")[0])

    def test_tags_render_as_pills_alone(self):
        page = render({**ASYNCAPI_V3, "servers": {"production": {
            "host": "b", "tags": [{"name": "env:prod"}]}}})
        self.assertIn("techdocs-owl-api-pill", page)
        self.assertIn(">env:prod</span>", page)
        self.assertNotIn("**Tags:**", page)

    def test_merged_trait_reaches_the_message(self):
        page = render(ASYNCAPI_V3)
        message = page.split("### LightMeasured")[1].split("## ")[0]
        self.assertIn("**Headers**", message)
        self.assertIn("my-app-header", message)

    def test_payload_links_to_the_schema_section(self):
        self.assertIn("[`lightMeasuredPayload`](#schemas-lightmeasuredpayload)",
                      render(ASYNCAPI_V3))

    def test_bindings_render_as_yaml(self):
        self.assertIn("mqtt bindings", render(ASYNCAPI_V3))
        self.assertNotIn("mqtt bindings", render(ASYNCAPI_V3, hide_bindings=True))

    def test_options_are_honoured(self):
        self.assertIn("# Custom", render(ASYNCAPI_V3, title="Custom"))
        self.assertNotIn("**Version:**", render(ASYNCAPI_V3, hide_version=True))
        self.assertNotIn("Security: apiKey", render(ASYNCAPI_V3, hide_security=True))

    def test_security_is_rendered_for_a_server(self):
        self.assertIn("Security: apiKey", render(ASYNCAPI_V2))


if __name__ == "__main__":
    unittest.main()
