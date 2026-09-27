"""Clé API-FOOTBALL facultative et jamais affichée (config.py)."""
from __future__ import annotations

from foot_predictor.config import Settings

POSTGRES = {"postgres_user": "u", "postgres_password": "p", "postgres_db": "d"}


def test_api_football_key_is_optional(monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    settings = Settings(_env_file=None, **POSTGRES)
    assert settings.api_football_key is None


def test_api_football_key_is_masked(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "cle-de-test-123")
    settings = Settings(_env_file=None, **POSTGRES)

    assert settings.api_football_key.get_secret_value() == "cle-de-test-123"
    assert "cle-de-test-123" not in repr(settings)
    assert "cle-de-test-123" not in str(settings.api_football_key)
