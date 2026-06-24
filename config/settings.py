from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.broker",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_host: str = "127.0.0.1"
    api_port: int = 9001

    lmstudio_base_url: str = "http://localhost:1234/v1"
    lmstudio_model: str = "local-model"
    lmstudio_api_key: str = "lm-studio"

    bot_enabled: bool = False
    bot_symbols: str = "SPY"

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip().upper() for s in self.bot_symbols.split(",") if s.strip()]


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
