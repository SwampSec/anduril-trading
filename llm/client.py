from __future__ import annotations

import asyncio

from openai import OpenAI

from config.settings import AppSettings
from llm.discovery import is_auto_model, pick_model_id


class LMStudioClient:
    """OpenAI-compatible client for local LM Studio (headlines only — no account data)."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._client = OpenAI(
            base_url=settings.lmstudio_base_url,
            api_key=settings.lmstudio_api_key,
        )
        self._cached_model_id: str | None = None

    def list_model_ids(self) -> list[str]:
        models = self._client.models.list()
        return [m.id for m in models.data]

    def resolve_model_id(self, *, refresh: bool = False) -> str:
        configured = self.settings.lmstudio_model
        if (
            not refresh
            and self._cached_model_id
            and is_auto_model(configured)
        ):
            return self._cached_model_id

        model_id = pick_model_id(self.list_model_ids(), configured)
        if is_auto_model(configured):
            self._cached_model_id = model_id
        return model_id

    def complete(self, prompt: str) -> str:
        model_id = self.resolve_model_id(refresh=is_auto_model(self.settings.lmstudio_model))
        response = self._client.chat.completions.create(
            model=model_id,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or "{}"

    async def complete_async(self, prompt: str) -> str:
        return await asyncio.to_thread(self.complete, prompt)

    def ping(self) -> dict[str, str | bool]:
        try:
            model_ids = self.list_model_ids()
            active = pick_model_id(model_ids, self.settings.lmstudio_model)
            if is_auto_model(self.settings.lmstudio_model):
                self._cached_model_id = active
            return {
                "ok": True,
                "base_url": self.settings.lmstudio_base_url,
                "auto_model": is_auto_model(self.settings.lmstudio_model),
                "active_model": active,
                "models": ", ".join(model_ids[:5]),
                "model_count": len(model_ids),
            }
        except Exception as exc:
            return {
                "ok": False,
                "base_url": self.settings.lmstudio_base_url,
                "auto_model": is_auto_model(self.settings.lmstudio_model),
                "error": str(exc),
            }
