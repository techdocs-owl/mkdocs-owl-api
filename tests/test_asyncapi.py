from __future__ import annotations

import unittest

from mkdocs_owl_api.render.asyncapi import _render_page


class TestAsyncAPI(unittest.TestCase):
    V2 = {
        "asyncapi": "2.6.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "servers": {"broker": {"protocol": "kafka-secure", "url": "h:9092",
                               "tags": [{"name": "prod"}],
                               "security": [{"creds": []}]}},
        "channels": {
            "CANCEL": {
                "subscribe": {
                    "operationId": "onCancel",
                    "summary": "Cancel events",
                    "tags": [{"name": "orders"}],
                    "message": {
                        "name": "cancelMsg", "contentType": "application/json",
                        "payload": {"type": "object", "required": ["id"],
                                    "properties": {"id": {"type": "string"}}},
                    },
                },
            },
            "ORDERS": {
                "subscribe": {"operationId": "onOrder",
                              "message": {"$ref": "#/components/messages/order"}},
            },
        },
        "components": {
            "securitySchemes": {"creds": {"type": "scramSha512",
                                          "description": "creds"}},
            "messages": {"order": {"name": "order", "contentType": "application/json",
                                   "payload": {"type": "object",
                                               "properties": {"x": {"type": "string"}}}}},
        },
    }

    V3 = {
        "asyncapi": "3.0.0",
        "info": {"title": "Demo3", "version": "1.0.0"},
        "channels": {"orders": {"address": "demo.orders"}},
        "operations": {
            "onOrder": {"action": "receive", "deprecated": True,
                        "tags": [{"name": "orders"}],
                        "channel": {"$ref": "#/channels/orders"}},
        },
        "components": {},
    }

    def test_operations_no_channels(self):
        md = _render_page(self.V2, {})
        self.assertIn("## Operations", md)
        self.assertNotIn("## Channels", md)

    def test_operations_channel_pill(self):
        md = _render_page(self.V2, {})
        self.assertIn("techdocs-owl-api-pill--action-subscribe", md)
        self.assertIn("**Channel:** `CANCEL`", md)

    def test_messages_inline_heading(self):
        md = _render_page(self.V2, {})
        self.assertIn("**Message: cancelMsg**", md)
        self.assertNotIn("#### cancelMsg", md)
        self.assertIn("techdocs-owl-api-pill--contenttype", md)
        self.assertIn("<code>id</code>", md)

    def test_messages_ref_link(self):
        md = _render_page(self.V2, {})
        self.assertIn("**Message:** [`order`](#messages-order)", md)

    def test_security_admonition(self):
        md = _render_page(self.V2, {})
        self.assertIn('!!! note ":material-security: Security: creds"', md)
        self.assertNotIn("??? note", md)

    def test_operations_deprecated(self):
        md = _render_page(self.V3, {})
        self.assertIn("## Operations", md)
        self.assertIn("techdocs-owl-api-pill--action-receive", md)
        self.assertIn("techdocs-owl-api-pill--deprecated", md)
        self.assertIn("**Channel:** `demo.orders`", md)

    def test_messages_payload(self):
        md = _render_page(self.V2, {})
        i = md.find("## Messages")
        self.assertNotIn("_inline schema_", md[i:])

    def test_traits_bindings(self):
        spec = {
            "asyncapi": "2.6.0", "info": {"title": "B", "version": "1"},
            "channels": {"c": {"subscribe": {"operationId": "op",
                          "bindings": {"kafka": {"groupId": "g"}},
                          "message": {"name": "m",
                                      "payload": {"type": "object"}}}}},
            "components": {"operationTraits": {"t": {
                "bindings": {"kafka": {"clientId": "c"}}}}},
        }
        md = _render_page(spec, {})
        self.assertIn('!!! note "kafka bindings"', md)
        self.assertNotIn("??? note", md)
        ot = md.find("## Operation traits")
        self.assertNotEqual(ot, -1)
        self.assertNotIn("bindings", md[ot:])


if __name__ == "__main__":
    unittest.main(verbosity=2)
