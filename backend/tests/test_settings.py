import pytest
from pydantic import ValidationError

from app.settings import Settings


def make(**overrides) -> Settings:
    base = {"_env_file": None}
    base.update(overrides)
    return Settings(**base)


def test_defaults_are_development_friendly():
    s = make()
    assert s.env == "development"
    assert s.auth_backend == "dev"
    assert s.data_level == 0
    assert s.database_url.startswith("sqlite:///")
    assert s.theme_look == "pixel"
    assert s.training_interval_days == 365


def test_list_fields_accept_comma_separated_strings():
    s = make(admin_groups="compliance, it-admins", proxy_trusted_addresses="10.0.0.1")
    assert s.admin_groups == ["compliance", "it-admins"]
    assert s.proxy_trusted_addresses == ["10.0.0.1"]


def test_list_fields_parse_from_real_environment(monkeypatch):
    monkeypatch.setenv("ADMIN_GROUPS", "compliance, it-admins")
    monkeypatch.setenv("PROXY_TRUSTED_ADDRESSES", "10.0.0.1,10.0.0.2")
    s = Settings(_env_file=None)
    assert s.admin_groups == ["compliance", "it-admins"]
    assert s.proxy_trusted_addresses == ["10.0.0.1", "10.0.0.2"]


def test_dev_auth_refused_in_production():
    with pytest.raises(ValidationError, match="AUTH_BACKEND=dev"):
        make(env="production", auth_backend="dev", secret_key="x" * 32)


def test_default_secret_refused_in_production():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make(env="production", auth_backend="oidc")


def test_audit_log_requires_level_two():
    with pytest.raises(ValidationError, match="FEATURE_AUDIT_LOG"):
        make(feature_audit_log=True, data_level=1)
    assert make(feature_audit_log=True, data_level=2).feature_audit_log is True


def test_reminders_require_smtp_host():
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        make(feature_reminders=True)
    assert make(feature_reminders=True, smtp_host="mail.example").feature_reminders is True


def test_proxy_auth_requires_trusted_addresses():
    with pytest.raises(ValidationError, match="PROXY_TRUSTED_ADDRESSES"):
        make(auth_backend="proxy")


def test_all_problems_are_reported_together():
    with pytest.raises(ValidationError) as exc:
        make(feature_audit_log=True, feature_reminders=True)
    text = str(exc.value)
    assert "FEATURE_AUDIT_LOG" in text
    assert "SMTP_HOST" in text


def test_empty_optional_strings_become_none():
    s = make(smtp_host="", llm_model_embed="")
    assert s.smtp_host is None
    assert s.llm_model_embed is None


def test_empty_path_variable_is_rejected():
    with pytest.raises(ValidationError, match="must not be empty"):
        make(content_dir="")


def test_data_level_parses_from_real_environment(monkeypatch):
    monkeypatch.setenv("DATA_LEVEL", "2")
    s = Settings(_env_file=None)
    assert s.data_level == 2


@pytest.mark.parametrize("value", ["#fff", "rebeccapurple"])
def test_theme_colors_must_be_six_digit_hex(value):
    with pytest.raises(ValidationError):
        make(theme_primary=value)
    with pytest.raises(ValidationError):
        make(theme_background=value)


def test_invite_auth_is_allowed_in_production():
    s = make(env="production", auth_backend="invite", secret_key="x" * 32, litellm_admin_key="sk-a")
    assert s.auth_backend == "invite"


def test_invite_auth_requires_the_proxy_admin_key():
    with pytest.raises(ValidationError, match="AUTH_BACKEND=invite requires LITELLM_ADMIN_KEY"):
        make(auth_backend="invite")
