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


def test_settings_native_file_secret_source_is_redacted(tmp_path, monkeypatch):
    secret = "postgresql+psycopg://runtime:synthetic-private-password@postgres/altvia_test"
    (tmp_path / "ALTVIA_DATABASE_URL").write_text(secret, encoding="utf-8")
    monkeypatch.delenv("ALTVIA_DATABASE_URL", raising=False)
    monkeypatch.setenv("ALTVIA_PUBLIC_ORIGIN", "https://example.test")
    settings = Settings(_env_file=None, _secrets_dir=tmp_path)
    assert settings.database_url.get_secret_value() == secret
    assert secret not in repr(settings)


def test_invalid_file_secret_fails_without_disclosure(tmp_path, monkeypatch):
    secret = "mysql://runtime:synthetic-private-password@postgres/altvia_test"
    (tmp_path / "ALTVIA_DATABASE_URL").write_text(secret, encoding="utf-8")
    monkeypatch.delenv("ALTVIA_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, _secrets_dir=tmp_path, public_origin="https://example.test")
    assert secret not in str(error.value)


def test_explicit_configuration_retains_precedence_over_file_secret(tmp_path):
    (tmp_path / "ALTVIA_DATABASE_URL").write_text("invalid secret", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        _secrets_dir=tmp_path,
        database_url="postgresql+psycopg://localhost/explicit",
        public_origin="https://example.test",
    )
    assert settings.database_url.get_secret_value().endswith("/explicit")
