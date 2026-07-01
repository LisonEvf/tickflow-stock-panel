"""Provider registry."""
from __future__ import annotations

from app.data_providers.opentdx_provider import OpenTDXProvider

_PROVIDERS = {
    "opentdx": OpenTDXProvider,
}


def get_provider(name: str = "opentdx"):
    provider_cls = _PROVIDERS.get((name or "opentdx").lower())
    if provider_cls is None:
        raise ValueError(f"Unsupported data provider: {name}")
    return provider_cls()
