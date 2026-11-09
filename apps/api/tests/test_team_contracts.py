import pytest
from altvia.config import Settings
from altvia.main import create_app


@pytest.fixture(scope="module")
def patch_schema():
    # Export the real route schema without connecting to a database.
    app = create_app(
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://unused@localhost/unused",
            public_origin="https://example.test",
        )
    )
    schema = app.openapi()
    body = schema["paths"]["/api/v1/teams/{team_id}"]["patch"]["requestBody"]
    reference = body["content"]["application/json"]["schema"]["$ref"]
    return schema["components"]["schemas"][reference.rsplit("/", 1)[-1]]


def test_patch_contract_excludes_explicit_null(patch_schema):
    assert patch_schema["properties"]["name"].get("type") == "string"
    assert patch_schema["properties"]["active"].get("type") == "boolean"


def test_patch_contract_never_supplies_invalid_null_defaults(patch_schema):
    assert "default" not in patch_schema["properties"]["name"]
    assert "default" not in patch_schema["properties"]["active"]


def test_patch_contract_requires_a_known_field(patch_schema):
    assert patch_schema.get("minProperties", 0) >= 1
    assert patch_schema["additionalProperties"] is False
