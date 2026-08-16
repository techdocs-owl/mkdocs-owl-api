from __future__ import annotations

import unittest
from dataclasses import replace

from mkdocs_owl_api.model.asyncapi.types import (
    AsyncApiDialect,
    OperationAction,
    SecurityRequirement,
    SecuritySchemeType,
)
from mkdocs_owl_api.model.asyncapi.parser import parse_document

from ...fixtures import ASYNCAPI_V2, ASYNCAPI_V3


class ParserTestCase(unittest.TestCase):
    """`read` asserts a clean parse, so shape tests cannot pass while warning."""

    def parse(self, raw):
        result = parse_document(raw)
        return result.doc, result.warnings

    def read(self, raw):
        doc, warnings = self.parse(raw)
        self.assertEqual(warnings, (),
                         f"expected a clean parse: {[str(w) for w in warnings]}")
        return doc


def minimal_v2(**root):
    base = {"asyncapi": "2.6.0", "info": {"title": "T", "version": "1"}}
    base.update(root)
    return base


def minimal_v3(**root):
    base = {"asyncapi": "3.0.0", "info": {"title": "T", "version": "1"}}
    base.update(root)
    return base


class TestDialectDetection(ParserTestCase):
    def test_versions(self):
        for version, expected in (("2.0.0", AsyncApiDialect.V2),
                                  ("2.6.0", AsyncApiDialect.V2),
                                  ("3.0.0", AsyncApiDialect.V3)):
            with self.subTest(version=version):
                doc = self.read({"asyncapi": version,
                                 "info": {"title": "T", "version": "1"}})
                self.assertEqual(doc.dialect, expected)
                self.assertEqual(doc.spec_version, version)

    def test_version_line(self):
        self.assertEqual(self.read(ASYNCAPI_V2).spec_version_key, "asyncapi")

    def test_unknown_version_falls_back(self):
        doc, warnings = self.parse({"asyncapi": "4.0.0",
                                    "info": {"title": "T", "version": "1"}})
        self.assertEqual(doc.dialect, AsyncApiDialect.V3)
        self.assertIn("reading it as 3.0", warnings[0].message)

    def test_missing_version_warns_but_parses(self):
        doc, warnings = self.parse({"info": {"title": "T", "version": "1"}})
        self.assertEqual(doc.info.title, "T")
        self.assertIn("no `asyncapi` version", warnings[0].message)


class TestServers(ParserTestCase):
    def test_v2_url_splits_into_host_and_pathname(self):
        doc = self.read(minimal_v2(servers={"prod": {
            "url": "mqtt://broker.example.test:8883/events", "protocol": "mqtt"}}))
        server = doc.servers[0]
        self.assertEqual((server.host, server.pathname, server.protocol),
                         ("broker.example.test:8883", "/events", "mqtt"))

    def test_v2_url_without_a_path(self):
        doc = self.read(minimal_v2(servers={"prod": {
            "url": "mqtt://broker.example.test", "protocol": "mqtt"}}))
        self.assertIsNone(doc.servers[0].pathname)

    def test_v2_protocol_can_come_from_the_url(self):
        doc = self.read(minimal_v2(servers={"prod": {"url": "amqp://broker"}}))
        self.assertEqual(doc.servers[0].protocol, "amqp")

    def test_v3_states_the_parts_directly(self):
        doc = self.read(minimal_v3(servers={"prod": {
            "host": "broker.example.test", "protocol": "mqtt",
            "pathname": "/events"}}))
        server = doc.servers[0]
        self.assertEqual((server.host, server.pathname), ("broker.example.test", "/events"))

    def test_url_reassembles(self):
        doc = self.read(minimal_v3(servers={"prod": {
            "host": "broker", "protocol": "mqtt", "pathname": "/events"}}))
        self.assertEqual(doc.servers[0].url, "mqtt://broker/events")


class TestActions(ParserTestCase):
    """The inversion: 2.x says what a client does, 3.0 what the application does."""

    def test_publish_is_received_by_the_application(self):
        doc = self.read(minimal_v2(channels={"a/b": {"publish": {"operationId": "op"}}}))
        self.assertEqual(doc.operations[0].action, OperationAction.RECEIVE)

    def test_subscribe_is_sent_by_the_application(self):
        doc = self.read(minimal_v2(channels={"a/b": {"subscribe": {"operationId": "op"}}}))
        self.assertEqual(doc.operations[0].action, OperationAction.SEND)

    def test_v3_states_the_action(self):
        doc = self.read(minimal_v3(
            channels={"c": {"address": "a/b"}},
            operations={"op": {"action": "send", "channel": {"$ref": "#/channels/c"}}},
        ))
        self.assertEqual(doc.operations[0].action, OperationAction.SEND)

    def test_unknown_action_is_dropped(self):
        doc, warnings = self.parse(minimal_v3(
            channels={"c": {"address": "a/b"}},
            operations={"op": {"action": "shout", "channel": {"$ref": "#/channels/c"}}},
        ))
        self.assertEqual(doc.operations, ())
        self.assertIn("unknown action", warnings[0].message)

    def test_operation_names_its_channel_by_address(self):
        doc = self.read(minimal_v3(
            channels={"lightMeasured": {"address": "light/measured"}},
            operations={"op": {"action": "receive",
                               "channel": {"$ref": "#/channels/lightMeasured"}}},
        ))
        self.assertEqual(doc.operations[0].channel, "light/measured")


class TestTraits(ParserTestCase):
    def test_message_traits_are_merged(self):
        doc = self.read(minimal_v2(components={
            "messageTraits": {"common": {"contentType": "application/json"}},
            "messages": {"M": {"traits": [{"$ref": "#/components/messageTraits/common"}],
                               "summary": "A message."}},
        }))
        message = doc.components.messages["M"]
        self.assertEqual(message.content_type, "application/json")
        self.assertEqual(message.summary, "A message.")
        self.assertEqual(message.trait_names, ("common",))

    def test_the_object_wins_over_its_traits(self):
        doc = self.read(minimal_v2(components={
            "messageTraits": {"common": {"contentType": "application/xml"}},
            "messages": {"M": {"traits": [{"$ref": "#/components/messageTraits/common"}],
                               "contentType": "application/json"}},
        }))
        self.assertEqual(doc.components.messages["M"].content_type, "application/json")

    def test_operation_traits_are_merged(self):
        doc = self.read(minimal_v3(
            channels={"c": {"address": "a/b"}},
            operations={"op": {
                "action": "send", "channel": {"$ref": "#/channels/c"},
                "traits": [{"$ref": "#/components/operationTraits/kafka"}],
            }},
            components={"operationTraits": {"kafka": {"summary": "From the trait."}}},
        ))
        operation = doc.operations[0]
        self.assertEqual(operation.summary, "From the trait.")
        self.assertEqual(operation.trait_names, ("kafka",))


class TestSecurity(ParserTestCase):
    def test_v2_lists_scheme_names_with_scopes(self):
        doc = self.read(minimal_v2(servers={"prod": {
            "url": "mqtt://b", "security": [{"apiKey": ["read"]}]}}))
        self.assertEqual(doc.servers[0].security,
                         ((SecurityRequirement("apiKey", ("read",)),),))

    def test_v3_lists_the_schemes_themselves(self):
        doc = self.read(minimal_v3(
            servers={"prod": {"host": "b", "security": [
                {"$ref": "#/components/securitySchemes/apiKey"}]}},
            components={"securitySchemes": {"apiKey": {"type": "userPassword"}}},
        ))
        self.assertEqual(doc.servers[0].security,
                         ((SecurityRequirement("apiKey", ()),),))

    def test_scheme_types_beyond_http(self):
        doc = self.read(minimal_v3(components={"securitySchemes": {
            "scram": {"type": "scramSha256"}}}))
        self.assertEqual(doc.components.security_schemes["scram"].type,
                         SecuritySchemeType.SCRAM_SHA256)

    def test_unknown_scheme_type_is_dropped(self):
        doc, warnings = self.parse(minimal_v3(components={"securitySchemes": {
            "x": {"type": "magic"}}}))
        self.assertEqual(doc.components.security_schemes, {})
        self.assertIn("unknown security scheme type", warnings[0].message)


class TestParameters(ParserTestCase):
    def test_v2_nests_the_facts_in_a_schema(self):
        doc = self.read(minimal_v2(channels={"a/{id}": {"parameters": {"id": {
            "description": "An id.", "schema": {"type": "string", "enum": ["a", "b"]}}}}}))
        parameter = doc.channels[0].parameters["id"]
        self.assertEqual(parameter.description, "An id.")
        self.assertEqual(parameter.schema.enum, ("a", "b"))

    def test_v3_states_them_directly(self):
        doc = self.read(minimal_v3(channels={"c": {
            "address": "a/{id}",
            "parameters": {"id": {"description": "An id.", "enum": ["a", "b"]}}}}))
        parameter = doc.channels[0].parameters["id"]
        self.assertEqual(parameter.description, "An id.")
        self.assertEqual(parameter.schema.enum, ("a", "b"))

    def test_a_parameter_is_a_string_where_none_is_declared(self):
        # An address placeholder is substituted textually, so a parameter the
        # source gives no type to is a string.
        doc = self.read(minimal_v3(channels={"c": {
            "address": "a/{id}", "parameters": {"id": {"description": "An id."}}}}))
        self.assertEqual(doc.channels[0].parameters["id"].schema.types, ("string",))

    def test_a_declared_type_is_kept(self):
        doc = self.read(minimal_v2(channels={"a/{id}": {"parameters": {"id": {
            "schema": {"type": "integer", "minimum": 1}}}}}))
        schema = doc.channels[0].parameters["id"].schema
        self.assertEqual(schema.types, ("integer",))
        self.assertEqual(schema.numeric_constraints.minimum, 1)


class TestMessages(ParserTestCase):
    def test_v2_one_of_becomes_several_messages(self):
        doc = self.read(minimal_v2(channels={"a/b": {"publish": {"message": {"oneOf": [
            {"name": "First"}, {"name": "Second"}]}}}}))
        self.assertEqual(sorted(doc.channels[0].messages), ["First", "Second"])
        self.assertEqual(sorted(doc.operations[0].message_names), ["First", "Second"])

    def test_v2_message_reference_keeps_the_component_name(self):
        doc = self.read(minimal_v2(
            channels={"a/b": {"publish": {"message": {
                "$ref": "#/components/messages/LightMeasured"}}}},
            components={"messages": {"LightMeasured": {"summary": "S"}}},
        ))
        self.assertEqual(list(doc.channels[0].messages), ["LightMeasured"])


class TestParseDocument(ParserTestCase):
    """The entry point, over the same API written both ways."""

    def testV2Parse(self):
        doc = self.read(ASYNCAPI_V2)
        self.assertEqual(doc.dialect, AsyncApiDialect.V2)
        self.assertEqual(doc.spec_version, "2.6.0")

    def testV3Parse(self):
        doc = self.read(ASYNCAPI_V3)
        self.assertEqual(doc.dialect, AsyncApiDialect.V3)
        self.assertEqual(doc.spec_version, "3.0.0")

    def test_both_dialects_agree(self):
        v2, v3 = self.read(ASYNCAPI_V2), self.read(ASYNCAPI_V3)
        # A 2.x document keys its channels by address and a 3.0 one by a name of
        # its own; the address is the shared fact, so the key is normalised away.
        normalise = lambda doc: replace(
            doc, dialect=v3.dialect, spec_version="",
            channels=tuple(replace(c, name="") for c in doc.channels),
        )
        self.assertEqual(normalise(v2), normalise(v3))

    def test_channel_keys_really_do_differ(self):
        self.assertNotEqual(self.read(ASYNCAPI_V2).channels[0].name,
                            self.read(ASYNCAPI_V3).channels[0].name)


if __name__ == "__main__":
    unittest.main()
