"""Optional LM Studio / OpenAI-compatible LLM adapter."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / "Anduril" / ".env.trading")

DEFAULT_URL = os.getenv("LMSTUDIO_URL", "http://localhost:1234/v1")
DEFAULT_MODEL = os.getenv("LMSTUDIO_MODEL", "local-model")


def available() -> bool:
    try:
        r = requests.get(f"{DEFAULT_URL.rstrip('/')}/models", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def chat(system: str, user: str, max_tokens: int = 2048) -> tuple[str | None, str | None]:
    """Returns (text, error)."""
    try:
        r = requests.post(
            f"{DEFAULT_URL.rstrip('/')}/chat/completions",
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.4,
                "max_tokens": max_tokens,
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)


def format_context_json(ctx: dict) -> str:
    return json.dumps(ctx, indent=2, default=str)
