from pathlib import Path

import yaml

PUBLIC_OVERLAY = Path(__file__).resolve().parents[2] / "deploy" / "docker-compose.public.yml"


class ComposeLoader(yaml.SafeLoader):
    pass


# Compose's !reset tag is not YAML the stdlib knows; its value is irrelevant here.
ComposeLoader.add_constructor("!reset", lambda loader, node: None)


def trainer_environment() -> dict:
    overlay = yaml.load(PUBLIC_OVERLAY.read_text(encoding="utf-8"), Loader=ComposeLoader)
    return overlay["services"]["trainer"]["environment"]


def test_the_public_overlay_runs_production():
    assert trainer_environment()["ENV"] == "production"


def test_the_public_overlay_boots_invite_auth_not_dev():
    assert trainer_environment()["AUTH_BACKEND"] == "invite"


def test_the_public_overlay_has_no_default_secret_key():
    assert trainer_environment()["SECRET_KEY"].startswith("${SECRET_KEY:?")
