from __future__ import annotations

from app.services import ai_provider


def test_official_llm_provider_detects_configured_local_route(monkeypatch):
    monkeypatch.setattr(ai_provider, "current_ai_provider", lambda: ai_provider.OPENAI_COMPAT_PROVIDER)
    monkeypatch.setattr(ai_provider, "current_ai_base_url", lambda: "http://127.0.0.1:18080/v1")
    monkeypatch.setattr(ai_provider.settings, "llm_server_base_url", "http://127.0.0.1:18080")

    assert ai_provider.is_official_llm_provider() is True


def test_official_llm_provider_ignores_third_party_route(monkeypatch):
    monkeypatch.setattr(ai_provider, "current_ai_provider", lambda: ai_provider.OPENAI_COMPAT_PROVIDER)
    monkeypatch.setattr(ai_provider, "current_ai_base_url", lambda: "https://api.example.com/v1")
    monkeypatch.setattr(ai_provider.settings, "llm_server_base_url", "http://127.0.0.1:18080")

    assert ai_provider.is_official_llm_provider() is False
