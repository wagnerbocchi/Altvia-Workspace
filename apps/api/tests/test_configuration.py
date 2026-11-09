import pytest
from altvia.config import Settings
from pydantic import ValidationError


def test_invalid_database_configuration_never_discloses_credentials():
    value = "mysql://u:pass@x/db"
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url=value, public_origin="https://example.test")
    assert value not in str(error.value)
    assert "pass@" not in str(error.value)


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.test",
        "https://user:password@example.test",
        "https://example.test/path",
    ],
)
def test_unsafe_public_origin_is_rejected(origin):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://localhost/example",
            public_origin=origin,
        )
