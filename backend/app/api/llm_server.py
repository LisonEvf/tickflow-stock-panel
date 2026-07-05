"""Local Sub2API integration for the built-in LLM user center."""
from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import secrets_store
from app.config import settings

router = APIRouter(prefix="/api/llm-server", tags=["llm-server"])

LLM_SERVER_BASE_URL_KEY = "llm_server_base_url"
DEFAULT_LLM_MODEL = "gpt-5.5"


class LlmServerConfigIn(BaseModel):
    base_url: str


class UseLlmServerKeyIn(BaseModel):
    api_key: str
    model: str = DEFAULT_LLM_MODEL
    base_url: str | None = None
    user_agent: str = ""


def _normalize_base_url(raw: str) -> str:
    value = (raw or "").strip().rstrip("/")
    if not value:
        raise ValueError("LLM 服务器地址不能为空")

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("LLM 服务器地址必须是 http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("LLM 服务器地址不能包含用户名或密码")

    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _current_base_url() -> str:
    raw = secrets_store.load().get(LLM_SERVER_BASE_URL_KEY) or settings.llm_server_base_url
    return _normalize_base_url(str(raw))


def _gateway_base_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/v1"


def _config_payload(base_url: str) -> dict:
    return {
        "base_url": base_url,
        "gateway_base_url": _gateway_base_url(base_url),
    }


def _auth_headers(request: Request, *, required: bool) -> dict[str, str]:
    authorization = request.headers.get("authorization", "").strip()
    token = request.headers.get("x-sub2api-token", "").strip()
    if authorization:
        return {"Authorization": authorization}
    if token:
        return {"Authorization": f"Bearer {token}"}
    if required:
        raise HTTPException(status_code=401, detail="请先登录 LLM 服务账户")
    return {}


def _copy_passthrough_headers(request: Request, *, auth_required: bool) -> dict[str, str]:
    headers = _auth_headers(request, required=auth_required)
    for name in ("content-type", "accept-language"):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    return headers


def _unwrap_sub2api_response(resp: httpx.Response) -> dict | list | str | int | float | bool | None:
    if resp.status_code == 204:
        return {"ok": True}

    try:
        data = resp.json()
    except ValueError:
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
        return resp.text

    if resp.status_code >= 400:
        detail = data.get("message") or data.get("detail") or data.get("error") if isinstance(data, dict) else None
        raise HTTPException(status_code=resp.status_code, detail=detail or f"Sub2API HTTP {resp.status_code}")

    if isinstance(data, Mapping) and "code" in data:
        if data.get("code") == 0:
            return data.get("data")
        detail = data.get("message") or data.get("reason") or "Sub2API 请求失败"
        status = 401 if str(data.get("code")).upper() in {"401", "TOKEN_EXPIRED", "INVALID_TOKEN"} else 400
        raise HTTPException(status_code=status, detail=detail)

    return data


async def _forward(
    request: Request,
    method: str,
    upstream_path: str,
    *,
    auth_required: bool = True,
) -> dict | list | str | int | float | bool | None:
    base_url = _current_base_url()
    url = f"{base_url}/api/v1{upstream_path}"
    body = await request.body() if method in {"POST", "PUT", "PATCH", "DELETE"} else None
    headers = _copy_passthrough_headers(request, auth_required=auth_required)

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            resp = await client.request(
                method,
                url,
                params=request.query_params,
                content=body,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"无法连接 LLM 服务器: {exc}") from exc

    return _unwrap_sub2api_response(resp)


@router.get("/config")
def get_config() -> dict:
    return _config_payload(_current_base_url())


@router.put("/config")
def save_config(req: LlmServerConfigIn) -> dict:
    try:
        base_url = _normalize_base_url(req.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    secrets_store.save({LLM_SERVER_BASE_URL_KEY: base_url})
    settings.llm_server_base_url = base_url
    return _config_payload(base_url)


@router.get("/health")
async def health() -> dict:
    base_url = _current_base_url()
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            resp = await client.get(f"{base_url}/health")
    except httpx.HTTPError as exc:
        return {"ok": False, "base_url": base_url, "error": str(exc)}

    try:
        data = resp.json()
    except ValueError:
        data = resp.text[:500]
    return {
        "ok": resp.status_code < 400,
        "base_url": base_url,
        "status": resp.status_code,
        "data": data,
    }


@router.post("/auth/register")
async def register(request: Request):
    return await _forward(request, "POST", "/auth/register", auth_required=False)


@router.post("/auth/login")
async def login(request: Request):
    return await _forward(request, "POST", "/auth/login", auth_required=False)


@router.post("/auth/refresh")
async def refresh(request: Request):
    return await _forward(request, "POST", "/auth/refresh", auth_required=False)


@router.post("/auth/logout")
async def logout(request: Request):
    return await _forward(request, "POST", "/auth/logout", auth_required=False)


@router.get("/auth/me")
async def me(request: Request):
    return await _forward(request, "GET", "/auth/me")


@router.get("/settings/public")
async def public_settings(request: Request):
    return await _forward(request, "GET", "/settings/public", auth_required=False)


@router.get("/user/profile")
async def profile(request: Request):
    return await _forward(request, "GET", "/user/profile")


@router.get("/usage/dashboard/stats")
async def usage_dashboard_stats(request: Request):
    return await _forward(request, "GET", "/usage/dashboard/stats")


@router.get("/keys")
async def list_keys(request: Request):
    return await _forward(request, "GET", "/keys")


@router.post("/keys")
async def create_key(request: Request):
    return await _forward(request, "POST", "/keys")


@router.get("/keys/{key_id}")
async def get_key(key_id: int, request: Request):
    return await _forward(request, "GET", f"/keys/{key_id}")


@router.put("/keys/{key_id}")
async def update_key(key_id: int, request: Request):
    return await _forward(request, "PUT", f"/keys/{key_id}")


@router.delete("/keys/{key_id}")
async def delete_key(key_id: int, request: Request):
    return await _forward(request, "DELETE", f"/keys/{key_id}")


@router.get("/groups/available")
async def groups_available(request: Request):
    return await _forward(request, "GET", "/groups/available")


@router.get("/payment/config")
async def payment_config(request: Request):
    return await _forward(request, "GET", "/payment/config")


@router.get("/payment/checkout-info")
async def payment_checkout_info(request: Request):
    return await _forward(request, "GET", "/payment/checkout-info")


@router.get("/payment/plans")
async def payment_plans(request: Request):
    return await _forward(request, "GET", "/payment/plans")


@router.get("/payment/channels")
async def payment_channels(request: Request):
    return await _forward(request, "GET", "/payment/channels")


@router.get("/payment/limits")
async def payment_limits(request: Request):
    return await _forward(request, "GET", "/payment/limits")


@router.post("/payment/orders")
async def create_order(request: Request):
    return await _forward(request, "POST", "/payment/orders")


@router.get("/payment/orders/my")
async def my_orders(request: Request):
    return await _forward(request, "GET", "/payment/orders/my")


@router.get("/payment/orders/{order_id}")
async def get_order(order_id: int, request: Request):
    return await _forward(request, "GET", f"/payment/orders/{order_id}")


@router.post("/payment/orders/{order_id}/cancel")
async def cancel_order(order_id: int, request: Request):
    return await _forward(request, "POST", f"/payment/orders/{order_id}/cancel")


@router.post("/payment/orders/verify")
async def verify_order(request: Request):
    return await _forward(request, "POST", "/payment/orders/verify")


@router.post("/use")
def use_key(req: UseLlmServerKeyIn) -> dict:
    api_key = req.api_key.strip()
    model = req.model.strip() or DEFAULT_LLM_MODEL
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    try:
        base_url = _normalize_base_url(req.base_url or _current_base_url())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    gateway_base_url = _gateway_base_url(base_url)
    updates = {
        "ai_provider": "openai_compat",
        "ai_base_url": gateway_base_url,
        "ai_api_key": api_key,
        "ai_model": model,
    }
    if req.user_agent:
        updates["ai_user_agent"] = req.user_agent
    secrets_store.save(updates)
    settings.ai_provider = "openai_compat"
    settings.ai_base_url = gateway_base_url
    settings.ai_api_key = api_key
    settings.ai_model = model
    if req.user_agent:
        settings.ai_user_agent = req.user_agent

    return {
        "ok": True,
        "ai_provider": "openai_compat",
        "ai_base_url": gateway_base_url,
        "ai_api_key_masked": secrets_store.mask(api_key),
        "ai_model": model,
        "ai_configured": True,
    }
