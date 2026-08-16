from __future__ import annotations

import unittest

from mkdocs_owl_api.model.openapi.types import (
    HttpMethod,
    OpenApiDialect,
    ParameterLocation,
    SecurityRequirement,
    SecuritySchemeType,
)
from mkdocs_owl_api.model.openapi.parser import parse_document

from ...fixtures import API_V2, API_V30, API_V31, expected_api


class ParserTestCase(unittest.TestCase):
    """
    Base for parser tests.

    `read` asserts a clean parse. Most tests below check the shape of a model,
    and without this they would keep passing while the parser started
    complaining about their input.
    """

    def parse(self, raw):
        result = parse_document(raw)
        return result.doc, result.warnings

    def read(self, raw):
        doc, warnings = self.parse(raw)
        self.assertEqual(warnings, (),
                         f"expected a clean parse: {[str(w) for w in warnings]}")
        return doc


def minimal(**root):
    """A document with just enough to parse, plus whatever is under test."""
    base = {"openapi": "3.0.3", "info": {"title": "T", "version": "1"}}
    base.update(root)
    return base


def minimal_v2(**root):
    base = {"swagger": "2.0", "info": {"title": "T", "version": "1"}}
    base.update(root)
    return base


def only_operation(doc):
    return doc.paths[0].operations[0]


class TestDialectDetection(ParserTestCase):
    def test_versions(self):
        for version, expected in (("2.0", OpenApiDialect.V2_0),
                                  ("3.0.3", OpenApiDialect.V3_0),
                                  ("3.1.0", OpenApiDialect.V3_1)):
            with self.subTest(version=version):
                key = "swagger" if version == "2.0" else "openapi"
                doc = self.read({key: version, "info": {"title": "T", "version": "1"}})
                self.assertEqual(doc.dialect, expected)
                self.assertEqual(doc.spec_version, version)

    def test_version_line_is_renderable(self):
        for raw, expected in ((API_V2, "swagger: 2.0"),
                              (API_V30, "openapi: 3.0.3"),
                              (API_V31, "openapi: 3.1.0")):
            with self.subTest(expected=expected):
                doc = self.read(raw)
                self.assertEqual(f"{doc.spec_version_key}: {doc.spec_version}", expected)

    def test_unknown_version_falls_back(self):
        doc, warnings = self.parse({"openapi": "3.2.0", "info": {"title": "T", "version": "1"}})
        self.assertEqual(doc.dialect, OpenApiDialect.V3_1)
        self.assertEqual(doc.spec_version, "3.2.0")
        self.assertIn("reading it as 3.1", warnings[0].message)

    def test_missing_version_warns_but_parses(self):
        doc, warnings = self.parse({"info": {"title": "T", "version": "1"}})
        self.assertEqual(doc.info.title, "T")
        self.assertIn("no `openapi` or `swagger`", warnings[0].message)

    def test_non_object_yields_an_empty_document(self):
        doc, warnings = self.parse("nope")
        self.assertEqual(doc.info.title, "")
        self.assertEqual(len(warnings), 1)


class TestServers(ParserTestCase):
    def test_v2_crosses_schemes_with_host_and_base_path(self):
        doc = self.read(minimal_v2(host="api.example.test", basePath="/v1",
                                   schemes=["https", "http"]))
        self.assertEqual([s.url for s in doc.servers],
                         ["https://api.example.test/v1", "http://api.example.test/v1"])

    def test_v2_without_schemes_is_protocol_relative(self):
        doc = self.read(minimal_v2(host="api.example.test", basePath="/v1"))
        self.assertEqual([s.url for s in doc.servers], ["//api.example.test/v1"])

    def test_v2_without_host_or_base_path_has_none(self):
        self.assertEqual(self.read(minimal_v2()).servers, ())

    def test_v3_variables(self):
        doc = self.read(minimal(servers=[{
            "url": "https://{region}.example.test", "description": "Regional",
            "variables": {"region": {"default": "eu", "enum": ["eu", "us"],
                                     "description": "Region"}},
        }]))
        server = doc.servers[0]
        self.assertEqual(server.description, "Regional")
        self.assertEqual(server.variables["region"].default, "eu")
        self.assertEqual(server.variables["region"].enum, ("eu", "us"))

    def test_v3_variable_without_default_warns(self):
        _, warnings = self.parse(minimal(servers=[{"url": "https://x/{v}",
                                                   "variables": {"v": {}}}]))
        self.assertIn("no `default`", warnings[0].message)


class TestParameters(ParserTestCase):
    def test_v2_lifts_inline_schema_keywords(self):
        doc = self.read(minimal_v2(paths={"/x": {"get": {
            "parameters": [{"name": "limit", "in": "query", "type": "integer",
                            "format": "int32", "minimum": 1,
                            "description": "How many."}],
            "responses": {},
        }}}))
        parameter = only_operation(doc).parameters[0]
        self.assertEqual(parameter.schema.types, ("integer",))
        self.assertEqual(parameter.schema.format, "int32")
        self.assertEqual(parameter.schema.numeric_constraints.minimum, 1)
        # The parameter's own description stays on the parameter.
        self.assertEqual(parameter.description, "How many.")
        self.assertIsNone(parameter.schema.description)

    def test_v2_body_and_form_become_a_request_body(self):
        doc = self.read(minimal_v2(paths={"/x": {"post": {
            "parameters": [
                {"name": "q", "in": "query", "type": "string"},
                {"name": "body", "in": "body", "schema": {"type": "object"}},
                {"name": "f", "in": "formData", "type": "string"},
            ],
            "responses": {},
        }}}))
        self.assertEqual([p.name for p in only_operation(doc).parameters], ["q"])

    def test_collection_format_maps_to_style(self):
        cases = [
            ("csv", "query", ("form", None)),
            ("csv", "path", ("simple", None)),
            ("multi", "query", ("form", True)),
            ("ssv", "query", ("spaceDelimited", None)),
            ("pipes", "query", ("pipeDelimited", None)),
            # No 3.x equivalent exists, so it survives rather than vanishing.
            ("tsv", "query", ("tsv", None)),
        ]
        for collection_format, location, expected in cases:
            with self.subTest(collectionFormat=collection_format, location=location):
                doc = self.read(minimal_v2(paths={"/x": {"get": {
                    "parameters": [{"name": "p", "in": location, "type": "array",
                                    "required": location == "path",
                                    "collectionFormat": collection_format}],
                    "responses": {},
                }}}))
                parameter = only_operation(doc).parameters[0]
                self.assertEqual((parameter.style, parameter.explode), expected)

    def test_path_parameters_merge_into_operations(self):
        doc = self.read(minimal(paths={"/x": {
            "parameters": [{"name": "id", "in": "path", "required": True,
                            "schema": {"type": "string"}}],
            "get": {"parameters": [{"name": "q", "in": "query",
                                    "schema": {"type": "string"}}],
                    "responses": {}},
        }}))
        operation = only_operation(doc)
        self.assertEqual([p.name for p in operation.parameters], ["id", "q"])
        # The declared view stays on the path item.
        self.assertEqual([p.name for p in doc.paths[0].parameters], ["id"])

    def test_operation_wins_on_collision(self):
        doc = self.read(minimal(paths={"/x": {
            "parameters": [{"name": "id", "in": "path",
                            "description": "inherited",
                            "schema": {"type": "string"}}],
            "get": {"parameters": [{"name": "id", "in": "path",
                                    "description": "own",
                                    "schema": {"type": "string"}}],
                    "responses": {}},
        }}))
        parameters = only_operation(doc).parameters
        self.assertEqual(len(parameters), 1)
        self.assertEqual(parameters[0].description, "own")

    def test_same_name_different_location_both_kept(self):
        doc = self.read(minimal(paths={"/x": {"get": {
            "parameters": [{"name": "id", "in": "path", "schema": {"type": "string"}},
                           {"name": "id", "in": "query", "schema": {"type": "string"}}],
            "responses": {},
        }}}))
        self.assertEqual([p.location for p in only_operation(doc).parameters],
                         [ParameterLocation.PATH, ParameterLocation.QUERY])

    def test_unknown_location_is_dropped(self):
        doc, warnings = self.parse(minimal(paths={"/x": {"get": {
            "parameters": [{"name": "p", "in": "nowhere"}], "responses": {},
        }}}))
        self.assertEqual(only_operation(doc).parameters, ())
        self.assertIn("unknown location", warnings[0].message)


class TestRequestBody(ParserTestCase):
    def test_v2_body_parameter_becomes_a_request_body(self):
        doc = self.read(minimal_v2(consumes=["application/json"], paths={"/x": {"post": {
            "parameters": [{"name": "body", "in": "body", "required": True,
                            "description": "The thing.",
                            "schema": {"$ref": "#/definitions/Thing"}}],
            "responses": {},
        }}}))
        body = only_operation(doc).request_body
        self.assertEqual(body.description, "The thing.")
        self.assertTrue(body.required)
        self.assertEqual(body.content["application/json"].schema.ref_name, "Thing")

    def test_v2_body_without_consumes_defaults_to_json(self):
        doc = self.read(minimal_v2(paths={"/x": {"post": {
            "parameters": [{"name": "body", "in": "body",
                            "schema": {"type": "object"}}],
            "responses": {},
        }}}))
        self.assertEqual(list(only_operation(doc).request_body.content),
                         ["application/json"])

    def test_v2_form_data_becomes_an_object_schema(self):
        doc = self.read(minimal_v2(paths={"/x": {"post": {
            "parameters": [
                {"name": "name", "in": "formData", "type": "string", "required": True},
                {"name": "age", "in": "formData", "type": "integer"},
            ],
            "responses": {},
        }}}))
        body = only_operation(doc).request_body
        media = body.content["application/x-www-form-urlencoded"]
        self.assertEqual(sorted(media.schema.properties), ["age", "name"])
        self.assertEqual(media.schema.required, ("name",))
        self.assertTrue(body.required)

    def test_v2_file_upload_is_multipart(self):
        doc = self.read(minimal_v2(paths={"/x": {"post": {
            "parameters": [{"name": "file", "in": "formData", "type": "file"}],
            "responses": {},
        }}}))
        media = only_operation(doc).request_body.content["multipart/form-data"]
        uploaded = media.schema.properties["file"]
        self.assertEqual((uploaded.types, uploaded.format), (("string",), "binary"))

    def test_v3_request_body(self):
        doc = self.read(minimal(paths={"/x": {"post": {
            "requestBody": {"description": "The thing.", "required": True,
                            "content": {"application/json": {
                                "schema": {"$ref": "#/components/schemas/Thing"}}}},
            "responses": {},
        }}}))
        body = only_operation(doc).request_body
        self.assertTrue(body.required)
        self.assertEqual(body.content["application/json"].schema.ref_name, "Thing")

    def test_absent_request_body_is_none(self):
        doc = self.read(minimal(paths={"/x": {"get": {"responses": {}}}}))
        self.assertIsNone(only_operation(doc).request_body)


class TestResponses(ParserTestCase):
    def test_v2_crosses_schema_with_produces(self):
        doc = self.read(minimal_v2(produces=["application/json", "application/xml"],
                                   paths={"/x": {"get": {"responses": {
                                       "200": {"description": "ok",
                                               "schema": {"type": "string"}}}}}}))
        response = only_operation(doc).responses[0]
        self.assertEqual(sorted(response.content),
                         ["application/json", "application/xml"])
        self.assertEqual(response.content["application/xml"].schema.types, ("string",))

    def test_v2_operation_produces_overrides_the_document(self):
        doc = self.read(minimal_v2(produces=["application/json"], paths={"/x": {"get": {
            "produces": ["text/plain"],
            "responses": {"200": {"description": "ok", "schema": {"type": "string"}}},
        }}}))
        self.assertEqual(list(only_operation(doc).responses[0].content), ["text/plain"])

    def test_v2_examples_land_on_the_media_type(self):
        doc = self.read(minimal_v2(produces=["application/json"], paths={"/x": {"get": {
            "responses": {"200": {"description": "ok", "schema": {"type": "object"},
                                  "examples": {"application/json": {"a": 1}}}},
        }}}))
        self.assertEqual(
            only_operation(doc).responses[0].content["application/json"].example,
            {"a": 1},
        )

    def test_body_less_response_has_no_content(self):
        for raw in (minimal_v2(paths={"/x": {"delete": {
                        "responses": {"204": {"description": "gone"}}}}}),
                    minimal(paths={"/x": {"delete": {
                        "responses": {"204": {"description": "gone"}}}}})):
            with self.subTest(raw=raw.get("swagger") or raw.get("openapi")):
                response = only_operation(self.read(raw)).responses[0]
                self.assertEqual(response.content, {})
                self.assertEqual(response.status_code, "204")

    def test_status_keys_are_kept_verbatim(self):
        doc = self.read(minimal(paths={"/x": {"get": {"responses": {
            "200": {"description": "ok"}, "2XX": {"description": "other"},
            "default": {"description": "fallback"}}}}}))
        self.assertEqual([r.status_code for r in only_operation(doc).responses],
                         ["200", "2XX", "default"])

    def test_headers(self):
        doc = self.read(minimal_v2(paths={"/x": {"get": {"responses": {"200": {
            "description": "ok",
            "headers": {"X-Rate-Limit": {"type": "integer", "description": "Left."}},
        }}}}}))
        header = only_operation(doc).responses[0].headers["X-Rate-Limit"]
        self.assertEqual(header.schema.types, ("integer",))
        self.assertEqual(header.description, "Left.")


class TestSecurity(ParserTestCase):
    def test_v2_basic_becomes_http(self):
        doc = self.read(minimal_v2(securityDefinitions={"b": {"type": "basic"}}))
        scheme = doc.components.security_schemes["b"]
        self.assertEqual(scheme.type, SecuritySchemeType.HTTP)
        self.assertEqual(scheme.scheme, "basic")

    def test_v2_api_key(self):
        doc = self.read(minimal_v2(securityDefinitions={
            "k": {"type": "apiKey", "name": "X-Key", "in": "header"}}))
        scheme = doc.components.security_schemes["k"]
        self.assertEqual(scheme.parameter_name, "X-Key")
        self.assertEqual(scheme.location, ParameterLocation.HEADER)

    def test_v2_flow_names_map_onto_the_flows_object(self):
        cases = [("implicit", "implicit"), ("password", "password"),
                 ("application", "client_credentials"),
                 ("accessCode", "authorization_code")]
        for flow, field in cases:
            with self.subTest(flow=flow):
                doc = self.read(minimal_v2(securityDefinitions={"o": {
                    "type": "oauth2", "flow": flow,
                    "authorizationUrl": "https://a", "tokenUrl": "https://t",
                    "scopes": {"read": "Read"},
                }}))
                flows = doc.components.security_schemes["o"].flows
                self.assertIsNotNone(getattr(flows, field))
                self.assertEqual(getattr(flows, field).scopes, {"read": "Read"})

    def test_v2_unknown_flow_warns(self):
        _, warnings = self.parse(minimal_v2(securityDefinitions={
            "o": {"type": "oauth2", "flow": "magic"}}))
        self.assertIn("unknown OAuth flow", warnings[0].message)

    def test_v3_flows(self):
        doc = self.read(minimal(components={"securitySchemes": {"o": {
            "type": "oauth2",
            "flows": {"clientCredentials": {"tokenUrl": "https://t",
                                            "scopes": {"read": "Read"}}},
        }}}))
        flows = doc.components.security_schemes["o"].flows
        self.assertEqual(flows.client_credentials.token_url, "https://t")
        self.assertIsNone(flows.implicit)

    def test_requirements_nest_and_or(self):
        doc = self.read(minimal(security=[{"a": [], "b": ["scope"]}, {"c": []}]))
        self.assertEqual(doc.security, (
            (SecurityRequirement("a", ()), SecurityRequirement("b", ("scope",))),
            (SecurityRequirement("c", ()),),
        ))

    def test_operation_security_distinguishes_absent_from_empty(self):
        doc = self.read(minimal(paths={"/x": {
            "get": {"responses": {}},
            "post": {"security": [], "responses": {}},
        }}))
        by_method = {op.method: op for op in doc.paths[0].operations}
        self.assertIsNone(by_method[HttpMethod.GET].security)
        self.assertEqual(by_method[HttpMethod.POST].security, ())


class TestReferences(ParserTestCase):
    def test_v2_parameter_ref_is_inlined(self):
        doc = self.read(minimal_v2(
            parameters={"Page": {"name": "page", "in": "query", "type": "integer"}},
            paths={"/x": {"get": {"parameters": [{"$ref": "#/parameters/Page"}],
                                  "responses": {}}}}))
        parameter = only_operation(doc).parameters[0]
        self.assertEqual(parameter.name, "page")
        self.assertEqual(parameter.schema.types, ("integer",))

    def test_v3_response_ref_is_inlined(self):
        doc = self.read(minimal(
            components={"responses": {"NotFound": {"description": "Missing."}}},
            paths={"/x": {"get": {"responses": {
                "404": {"$ref": "#/components/responses/NotFound"}}}}}))
        response = only_operation(doc).responses[0]
        self.assertEqual((response.status_code, response.description),
                         ("404", "Missing."))

    def test_schema_refs_are_kept(self):
        doc = self.read(minimal(
            components={"schemas": {"Pet": {"type": "object"}}},
            paths={"/x": {"get": {"responses": {"200": {
                "description": "ok",
                "content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/Pet"}}}}}}}}))
        schema = only_operation(doc).responses[0].content["application/json"].schema
        self.assertTrue(schema.is_ref())
        self.assertEqual(schema.ref_name, "Pet")

    def test_dangling_ref_warns(self):
        _, warnings = self.parse(minimal(paths={"/x": {"get": {
            "parameters": [{"$ref": "#/components/parameters/Nope"}],
            "responses": {}}}}))
        self.assertIn("does not resolve", warnings[0].message)

    def test_circular_ref_warns_instead_of_hanging(self):
        _, warnings = self.parse(minimal(
            components={"parameters": {"A": {"$ref": "#/components/parameters/A"}}},
            paths={"/x": {"get": {"parameters": [{"$ref": "#/components/parameters/A"}],
                                  "responses": {}}}}))
        self.assertTrue(any("circular" in w.message for w in warnings))

    def test_escaped_pointer_tokens(self):
        doc = self.read(minimal(
            components={"parameters": {"a/b": {"name": "p", "in": "query"}}},
            paths={"/x": {"get": {
                "parameters": [{"$ref": "#/components/parameters/a~1b"}],
                "responses": {}}}}))
        self.assertEqual(only_operation(doc).parameters[0].name, "p")


class TestPaths(ParserTestCase):
    def test_operations_and_path_are_recorded(self):
        doc = self.read(minimal(paths={"/pets": {"get": {"responses": {}},
                                                 "post": {"responses": {}}}}))
        self.assertEqual([(o.method, o.path) for o in doc.paths[0].operations],
                         [(HttpMethod.GET, "/pets"), (HttpMethod.POST, "/pets")])

    def test_extension_keys_are_skipped(self):
        doc = self.read(minimal(paths={"/pets": {"get": {"responses": {}}},
                                       "x-internal": {"note": "ignore me"}}))
        self.assertEqual([p.path for p in doc.paths], ["/pets"])

    def test_one_bad_path_keeps_the_others(self):
        doc, warnings = self.parse(minimal(paths={"/good": {"get": {"responses": {}}},
                                                  "/bad": "nope"}))
        self.assertEqual([p.path for p in doc.paths], ["/good"])
        self.assertEqual(len(warnings), 1)


class TestParseDocument(ParserTestCase):
    """
    The entry point, over the whole API fixture.

    Each test asserts the complete document rather than sampling it, so anything
    invented, dropped or mistranslated fails here. The three expectations differ
    only in the dialect they declare and where their components live.
    """

    def testV2Parse(self):
        self.assertEqual(
            self.read(API_V2),
            expected_api(OpenApiDialect.V2_0, "2.0", "#/definitions/"),
        )

    def testV30Parse(self):
        self.assertEqual(
            self.read(API_V30),
            expected_api(OpenApiDialect.V3_0, "3.0.3", "#/components/schemas/"),
        )

    def testV31Parse(self):
        self.assertEqual(
            self.read(API_V31),
            expected_api(OpenApiDialect.V3_1, "3.1.0", "#/components/schemas/"),
        )


if __name__ == "__main__":
    unittest.main()
