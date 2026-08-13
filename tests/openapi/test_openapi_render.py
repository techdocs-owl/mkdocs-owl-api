from __future__ import annotations

import unittest

from mkdocs_owl_api.common.render import RenderContext
from mkdocs_owl_api.jsonschema.schema_model import (
    NumericConstraints,
    Schema,
    StringConstraints,
)
from mkdocs_owl_api.jsonschema.schema_render import (
    describe,
    format_type,
    property_rows,
    render_schema,
)
from mkdocs_owl_api.openapi import Renderer, parse_document
from mkdocs_owl_api.options import PageOptions

from ..fixtures import API_V2, API_V30, API_V31


def render(spec, **options):
    opts = PageOptions(type="openapi", spec="spec.json", **options)
    return Renderer(parse_document(spec).doc, RenderContext(options=opts)).render()


class TestFormatType(unittest.TestCase):
    def test_scalar(self):
        self.assertEqual(format_type(Schema(types=("string",))), "string")

    def test_format_is_appended(self):
        self.assertEqual(format_type(Schema(types=("integer",), format="int64")),
                         "integer (int64)")

    def test_union(self):
        self.assertEqual(format_type(Schema(types=("string", "integer"))),
                         "string | integer")

    def test_nullable_reads_as_a_union(self):
        self.assertEqual(format_type(Schema(types=("string",), nullable=True)),
                         "string | null")

    def test_array(self):
        self.assertEqual(
            format_type(Schema(types=("array",), items=Schema(types=("string",)))),
            "array of string",
        )

    def test_map(self):
        self.assertEqual(
            format_type(Schema(types=("object",),
                               additional_properties=Schema(types=("string",)))),
            "map of string → string",
        )

    def test_reference_links_to_the_schema_section(self):
        self.assertEqual(
            format_type(Schema(ref="#/definitions/Pet", ref_name="Pet")),
            "[`Pet`](#schemas-pet)",
        )

    def test_anchor_follows_the_component_name(self):
        # The anchor comes from the component name, so two documents that keep
        # their components in different places link to the same heading.
        self.assertEqual(
            format_type(Schema(ref="#/definitions/Pet", ref_name="Pet")),
            format_type(Schema(ref="#/components/schemas/Pet", ref_name="Pet")),
        )

    def test_lone_all_of_member_supplies_the_type(self):
        schema = Schema(all_of=(Schema(ref="#/c/Pet", ref_name="Pet"),))
        self.assertEqual(format_type(schema), "[`Pet`](#schemas-pet)")

    def test_unknown_is_object(self):
        self.assertEqual(format_type(Schema()), "object")
        self.assertEqual(format_type(None), "any")


class TestDescribe(unittest.TestCase):
    def test_description_only(self):
        self.assertEqual(describe(Schema(description="A pet.")), "A pet.")

    def test_constraints_are_labelled(self):
        text = describe(Schema(
            types=("string",),
            string_constraints=StringConstraints(min_length=1, pattern="^a"),
        ))
        self.assertIn("- Min length: `1`", text)
        self.assertIn("- Pattern: `^a`", text)

    def test_both_numeric_limits_are_shown(self):
        text = describe(Schema(
            types=("number",),
            numeric_constraints=NumericConstraints(minimum=1, exclusive_minimum=5),
        ))
        self.assertIn("- Minimum: `1`", text)
        self.assertIn("- Exclusive minimum: `5`", text)

    def test_constraints_heading_appears_only_beside_prose(self):
        self.assertNotIn("**Constraints**", describe(Schema(
            string_constraints=StringConstraints(min_length=1))))
        self.assertIn("**Constraints**", describe(Schema(
            description="A name.", string_constraints=StringConstraints(min_length=1))))

    def test_null_default_is_shown(self):
        self.assertIn("- Default: `None`", describe(Schema(default=None)))

    def test_absent_default_is_omitted(self):
        self.assertNotIn("Default", describe(Schema(types=("string",))))

    def test_closed_object_note(self):
        self.assertIn("NOT allowed", describe(Schema(additional_properties=False)))


class TestPropertyRows(unittest.TestCase):
    NESTED = Schema(
        types=("object",),
        required=("outer",),
        properties={"outer": Schema(
            types=("object",),
            properties={"inner": Schema(types=("string",))},
            required=("inner",),
        )},
    )

    def test_flat_paths(self):
        rows = property_rows(self.NESTED, max_depth=2)
        self.assertEqual([r.path for r in rows], ["outer", "outer.inner"])
        self.assertEqual([r.required for r in rows], [True, True])

    def test_depth_limits_expansion(self):
        rows = property_rows(self.NESTED, max_depth=1)
        self.assertEqual([r.path for r in rows], ["outer"])

    def test_array_of_objects_gets_a_bracket_path(self):
        schema = Schema(properties={"tags": Schema(
            types=("array",),
            items=Schema(types=("object",), properties={"id": Schema(types=("string",))}),
        )})
        rows = property_rows(schema, max_depth=2)
        self.assertEqual([r.path for r in rows], ["tags[]", "tags[].id"])
        self.assertEqual(rows[0].type_override, "array of objects")

    def test_a_reference_stays_a_single_row(self):
        schema = Schema(properties={"pet": Schema(ref="#/c/Pet", ref_name="Pet")})
        self.assertEqual([r.path for r in property_rows(schema, max_depth=5)], ["pet"])

    def test_internal_properties_can_be_hidden(self):
        schema = Schema(properties={
            "public": Schema(types=("string",)),
            "secret": Schema(types=("string",), extensions={"x-internal-only": True}),
        })
        self.assertEqual([r.path for r in property_rows(schema, hide_internal=True)],
                         ["public"])
        self.assertEqual(len(property_rows(schema, hide_internal=False)), 2)


class TestRenderSchema(unittest.TestCase):
    def test_enum_renders_as_a_constraint(self):
        blocks = render_schema(Schema(types=("string",), enum=("a", "b")))
        self.assertIn("`string`", blocks[0])
        self.assertIn("- Allowed values: `a`, `b`", blocks)

    def test_enum_survives_alongside_properties(self):
        blocks = "\n".join(render_schema(Schema(
            types=("object",),
            properties={"a": Schema(types=("integer",))},
            enum=({"a": 1},),
        )))
        self.assertIn("Allowed values", blocks)
        self.assertIn(">a</span>", blocks)

    def test_inline_all_of_members_merge_into_one_table(self):
        blocks = render_schema(Schema(
            types=("object",),
            properties={"own": Schema(types=("string",))},
            all_of=(Schema(properties={"borrowed": Schema(types=("string",))}),),
        ))
        table = "\n".join(blocks)
        self.assertIn("own", table)
        self.assertIn("borrowed", table)

    def test_referenced_all_of_members_are_linked(self):
        blocks = render_schema(Schema(
            types=("object",),
            all_of=(Schema(ref="#/c/Base", ref_name="Base"),),
            properties={"own": Schema(types=("string",))},
        ))
        self.assertIn("**All of:** [`Base`](#schemas-base)", blocks)


class TestPage(unittest.TestCase):
    """The whole page, over the same API written three ways."""

    def test_every_dialect_renders_the_same_page(self):
        pages = {name: render(spec) for name, spec in
                 (("2.0", API_V2), ("3.0", API_V30), ("3.1", API_V31))}
        # Only the specification line may differ - it names the source version.
        stripped = {
            name: "\n".join(line for line in page.split("\n")
                            if "**Specification:**" not in line)
            for name, page in pages.items()
        }
        self.assertEqual(stripped["2.0"], stripped["3.0"])
        self.assertEqual(stripped["3.0"], stripped["3.1"])

    def test_specification_line_names_the_source(self):
        self.assertIn("`swagger 2.0`", render(API_V2))
        self.assertIn("`openapi 3.1.0`", render(API_V31))

    def test_sections(self):
        page = render(API_V31)
        for expected in ("# Petstore", "**Version:** `1.0.0`", "## Servers",
                         "`https://api.example.test/v1`", "## pets {#tag-pets}",
                         "### List pets", "**Parameters**", "**Request body**",
                         "**Responses**", "## Schemas", "### Pet {#schemas-pet}"):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)

    def test_options_are_honoured(self):
        self.assertIn("# Custom", render(API_V31, title="Custom"))
        self.assertNotIn("**Version:**", render(API_V31, hide_version=True))
        self.assertNotIn("**Security**", render(API_V31, hide_security=True))

    def test_operation_security_opt_out_beats_the_document_default(self):
        page = render(API_V31)
        # `listPets` inherits the document requirement; `getPet` opted out with
        # an empty list, so it must show none.
        get_pet = page.split("### Get a pet")[1]
        self.assertNotIn("Security: api_key", get_pet)
        self.assertIn("Security: api_key", page.split("### Get a pet")[0])

    def test_response_headers_are_rendered(self):
        self.assertIn("X-Rate-Limit", render(API_V31))


if __name__ == "__main__":
    unittest.main()
