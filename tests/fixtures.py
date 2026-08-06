"""
Spec fixtures and the models they must parse to.

The inputs live in `jsons/` as real documents rather than Python literals: the
Pet schema written once per dialect, and a small API written once per dialect,
each enriched with the keywords that actually differ - nullability, exclusive
bounds, singular versus array examples, and `$ref` siblings.

Each is paired with an expectation built below. `expected_pet` and
`expected_api` take only a pointer prefix - and, for a document, the version it
declares - because that is all a dialect changes. Three inputs, one expectation,
is the claim that reading is dialect-independent stated in a form that cannot
drift.
"""

from __future__ import annotations

import json
from pathlib import Path

from mkdocs_owl_api.common.doc_model import Contact, ExternalDocs, Info, License, Tag
from mkdocs_owl_api.common.schema_model import (
    ArrayConstraints,
    NumericConstraints,
    Schema,
    StringConstraints,
)
from mkdocs_owl_api.openapi.model import (
    ApiDoc,
    Components,
    HttpMethod,
    MediaType,
    Operation,
    Parameter,
    ParameterLocation,
    PathItem,
    RequestBody,
    Response,
    SecurityRequirement,
    SecurityScheme,
    SecuritySchemeType,
    Server,
)
from mkdocs_owl_api.openapi.model import Header as ResponseHeader

_JSONS = Path(__file__).parent / "jsons"


def load(name: str) -> dict:
    """Read one of the JSON fixtures. A fresh object each call."""
    return json.loads((_JSONS / f"{name}.json").read_text(encoding="utf-8"))


#: The Pet schema, one file per dialect. The version in each name is the
#: OpenAPI version that spells it that way, not a JSON Schema draft.
#: `jsonschema-2.0` carries draft-4 bounds, `x-nullable`, `#/definitions/`
#: pointers and an `xml` object nothing models; `jsonschema-3.0` swaps in
#: `nullable` and `#/components/schemas/`; `jsonschema-3.1` uses numeric
#: exclusive bounds, `null` in the type array and `examples`.
PET_V2 = load("jsonschema-2.0")
PET_V30 = load("jsonschema-3.0")
PET_V31 = load("jsonschema-3.1")

#: The same API described three ways. `openapi-2.0` assembles its server from
#: `schemes`/`host`/`basePath`, puts its body in the parameter list and its
#: reusable objects at the root; the 3.x files use `servers`, `requestBody` and
#: `components`.
API_V2 = load("openapi-2.0")
API_V30 = load("openapi-3.0")
API_V31 = load("openapi-3.1")


# --------------------------------------------------------------------------
# How the documents in `jsons/` must parse. One builder per structure, taking the
# pointer prefix, because that is the only thing a dialect changes.
# --------------------------------------------------------------------------

def expected_pet(component_prefix):
    """
    The Pet fixture as it must parse, whichever dialect wrote it.

    Only the component pointers differ between dialects, so one builder serves
    all three - which is itself the claim that reading is dialect-independent.
    """
    def ref(name, **keywords):
        return Schema(ref=f"{component_prefix}{name}", ref_name=name, **keywords)

    return Schema(
        title="Pet",
        description="A pet in the store.",
        types=("object",),
        required=("name", "photoUrls"),
        properties={
            "id": Schema(types=("integer",), format="int64", read_only=True),
            "name": Schema(types=("string",), examples=("doggie",),
                           string_constraints=StringConstraints(min_length=1,
                                                                max_length=60)),
            "category": ref("Category", description="Grouping this pet belongs to."),
            "owner": ref("User", read_only=True),
            "photoUrls": Schema(types=("array",), items=Schema(types=("string",)),
                                array_constraints=ArrayConstraints(min_items=1,
                                                                   unique_items=True)),
            "tags": Schema(types=("array",), items=ref("Tag")),
            "status": Schema(types=("string",),
                             description="pet status in the store",
                             enum=("available", "pending", "sold"),
                             default="available"),
            "weight": Schema(types=("number",),
                             numeric_constraints=NumericConstraints(
                                 exclusive_minimum=0)),
            "nickname": Schema(types=("string",), nullable=True),
            "metadata": Schema(types=("object",),
                               additional_properties=Schema(types=("string",))),
            "notes": Schema(types=("string",), default=None),
        },
    )


def expected_api(dialect, spec_version, component_prefix):
    """The API fixture as it must parse, whichever dialect wrote it."""
    def ref(name):
        return Schema(ref=f"{component_prefix}{name}", ref_name=name)

    stub = Schema(
        types=("object",),
        properties={"id": Schema(types=("integer",)),
                    "name": Schema(types=("string",))},
    )
    error = Schema(types=("object",),
                   properties={"message": Schema(types=("string",))})
    page_size = Parameter(
        name="limit", location=ParameterLocation.QUERY, description="How many.",
        schema=Schema(types=("integer",), format="int32"),
    )
    json_pet = {"application/json": MediaType(schema=ref("Pet"))}

    listing = Operation(
        method=HttpMethod.GET, path="/pets", operation_id="listPets",
        summary="List pets", tags=("pets",), parameters=(page_size,),
        responses=(
            Response(status_code="200", description="A list.",
                     content={"application/json": MediaType(
                         schema=Schema(types=("array",), items=ref("Pet")))}),
            Response(status_code="default", description="Error.",
                     content={"application/json": MediaType(schema=ref("Error"))}),
        ),
    )
    adding = Operation(
        method=HttpMethod.POST, path="/pets", operation_id="addPet",
        summary="Add a pet", tags=("pets",),
        request_body=RequestBody(description="The pet.", required=True,
                                 content=json_pet),
        responses=(Response(status_code="201", description="Created.",
                            content=json_pet),),
    )
    pet_id = Parameter(
        name="petId", location=ParameterLocation.PATH, description="Pet id.",
        required=True, schema=Schema(types=("string",)),
    )
    getting = Operation(
        method=HttpMethod.GET, path="/pets/{petId}", operation_id="getPet",
        summary="Get a pet", tags=("pets",), parameters=(pet_id,),
        # An explicit empty list opts out of the document's security, which is
        # not the same as saying nothing.
        security=(),
        responses=(
            Response(status_code="200", description="The pet.",
                     headers={"X-Rate-Limit": ResponseHeader(
                         description="Calls left.",
                         schema=Schema(types=("integer",)))},
                     content=json_pet),
            Response(status_code="404", description="Missing."),
        ),
    )

    return ApiDoc(
        dialect=dialect,
        spec_version=spec_version,
        info=Info(
            title="Petstore", version="1.0.0", description="Pets, mostly.",
            contact=Contact(name="Team", email="team@example.test"),
            license=License(name="MIT"),
        ),
        servers=(Server(url="https://api.example.test/v1"),),
        tags=(Tag(name="pets", description="Pet operations"),),
        paths=(
            PathItem(path="/pets", operations=(listing, adding)),
            PathItem(path="/pets/{petId}", operations=(getting,),
                     parameters=(pet_id,)),
        ),
        components=Components(
            schemas={"Pet": expected_pet(component_prefix), "Error": error,
                     "Category": stub, "Tag": stub, "User": stub},
            parameters={"PageSize": page_size},
            security_schemes={"api_key": SecurityScheme(
                name="api_key", type=SecuritySchemeType.API_KEY,
                parameter_name="api_key", location=ParameterLocation.HEADER)},
        ),
        security=((SecurityRequirement("api_key", ()),),),
        external_docs=ExternalDocs(url="https://example.test/docs",
                                   description="More"),
    )
