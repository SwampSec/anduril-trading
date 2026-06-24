"""Thin HTTP client for the Anduril FastAPI control plane (localhost:9001)."""

from __future__ import annotations

import os
from typing import Any

import requests


def api_base_url() -> str:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = os.getenv("API_PORT", "9001")
    return os.getenv("ANDURIL_API_BASE", f"http://{host}:{port}").rstrip("/")


def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 12,
) -> dict[str, Any]:
    url = f"{api_base_url()}{path}"
    try:
        response = requests.request(method, url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)}

    if response.status_code >= 400:
        detail = response.text[:500]
        try:
            detail = response.json().get("detail", detail)
        except Exception:
            pass
        return {"ok": False, "status": response.status_code, "error": detail}

    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:500]}
    return {"ok": True, "data": data}
