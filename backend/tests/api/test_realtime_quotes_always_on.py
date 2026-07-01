from __future__ import annotations

from types import SimpleNamespace

from app.api.settings import RealtimeQuotesPrefs, update_realtime_quotes
from app.services import preferences


class _QuoteService:
    def __init__(self) -> None:
        self.enable_calls = 0

    def is_realtime_allowed(self) -> bool:
        return True

    def enable(self) -> bool:
        self.enable_calls += 1
        return True


def test_realtime_quotes_cannot_be_disabled(monkeypatch):
    saved: list[dict] = []
    monkeypatch.setattr(preferences, "save", lambda updates: saved.append(updates) or updates)
    qs = _QuoteService()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(quote_service=qs)))

    result = update_realtime_quotes(
        RealtimeQuotesPrefs(realtime_quotes_enabled=False),
        request,  # type: ignore[arg-type]
    )

    assert result == {"realtime_quotes_enabled": True, "realtime_allowed": True}
    assert saved == [{"realtime_quotes_enabled": True}]
    assert qs.enable_calls == 1
