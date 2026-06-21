from __future__ import annotations

import re
import unittest

from mkdocs_owl_api.render.openapi import _render_openapi_page


class TestOpenAPI(unittest.TestCase):
    SPEC = {
        "openapi": "3.0.3",
        "info": {"title": "Cat", "version": "1.0.0"},
        "servers": [{"url": "https://{region}.api/v{ver}", "description": "R",
                     "variables": {"region": {"default": "eu", "enum": ["eu", "us"],
                                              "description": "Region"},
                                   "ver": {"default": "1"}}}],
        "tags": [{"name": "Orders"}, {"name": "Admin"}],
        "paths": {
            "/orders/{id}": {
                "get": {
                    "tags": ["Orders", "Admin"],
                    "summary": "Get order",
                    "deprecated": True,
                    "parameters": [
                        {"name": "id", "in": "path", "required": True,
                         "schema": {"type": "string", "format": "uuid"},
                         "description": "Order id", "example": "abc-123"},
                        {"name": "fields", "in": "query", "deprecated": True,
                         "schema": {"type": "string", "enum": ["a", "b"], "default": "a"},
                         "description": "Filter"},
                    ],
                    "requestBody": {"content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Order"}},
                        "application/xml": {"schema": {"type": "string"}},
                    }},
                    "responses": {"200": {"description": "ok", "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Order"}},
                        "text/csv": {"schema": {"type": "string"}},
                    }}},
                    "security": [{"oauth": ["orders:read", "orders:write"]}],
                },
            },
        },
        "components": {
            "securitySchemes": {"oauth": {"type": "oauth2", "description": "OAuth2"}},
            "schemas": {"Order": {"type": "object",
                                  "properties": {"id": {"type": "string"}}}},
        },
    }

    def setUp(self):
        self.md = _render_openapi_page(self.SPEC, {})

    def test_servers_variables(self):
        self.assertIn("`{region}`", self.md)
        self.assertIn("default `eu`", self.md)
        self.assertIn("one of `eu`, `us`", self.md)

    def test_endpoints_unique_anchors(self):
        anchors = re.findall(r"\{#(endpoints-[^}]+)\}", self.md)
        self.assertEqual(len(anchors), len(set(anchors)))
        self.assertEqual(len(anchors), 2)

    def test_endpoints_deprecated(self):
        self.assertIn("techdocs-owl-api-pill--deprecated", self.md)

    def test_parameters_enrichment(self):
        self.assertIn("Example: <code>abc-123</code>", self.md)
        self.assertIn("Allowed values: <code>a</code>, <code>b</code>", self.md)
        self.assertIn("Default: <code>a</code>", self.md)

    def test_request_body_content_types(self):
        self.assertIn("application/json", self.md)
        self.assertIn("application/xml", self.md)

    def test_responses_content_types(self):
        self.assertIn("text/csv", self.md)

    def test_security_scopes(self):
        self.assertIn('!!! note ":material-security: Security: oauth"', self.md)
        self.assertIn("oauth2", self.md)
        self.assertIn("**Scopes:**", self.md)
        self.assertIn("orders:read", self.md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
