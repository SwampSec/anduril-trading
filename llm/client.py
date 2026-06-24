from __future__ import annotations

import asyncio

from openai import OpenAI

from config.settings import AppSettings


class LMStudioClient:
    """OpenAI-compatible client for local LM Studio (headlines only — no account data)."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._client = OpenAI(
            base_url=settings.lmstudio_base_url,
            api_key=settings.lmstudio_api_key,
        )

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.settings.lmstudio_model,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or "{}"

    async def complete_async(self, prompt: str) -> str:
        return await asyncio.to_thread(self.complete, prompt)

    def ping(self) -> dict[str, str | bool]:
        try:
            models = self._client.models.list()
            ids = [m.id for m in models.data]
            return {
                "ok": True,
                "base_url": self.settings.lmstudio_base_url,
                "models": ", ".join(ids[:5]),
            }
        except Exception as exc:
            return {
                "ok": False,
                "base_url": self.settings.lmstudio_base_url,
                "error": str(exc),
            }
