from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    admin_ids: str = ""
    database_path: str = "unipro.db"

    poll_interval_seconds: int = 60
    poll_concurrency: int = 5

    # Demo mode never mixes fake inventory with live inventory.
    demo_mode: bool = True
    enable_alibaba: bool = True
    enable_mrbilit: bool = True
    enable_safar724: bool = True
    enable_snapptrip: bool = True
    enable_flytoday: bool = True
    enable_raja: bool = False
    raja_api_key: str = ""
    raja_query_password: str = ""
    provider_timeout_seconds: float = 8.0

    health_port: int = 8080
    port: int | None = None  # injected by many PaaS providers

    min_transfer_minutes: int = 75
    max_transfer_wait_hours: int = 12
    alt_search_every_n_cycles: int = 5
    app_timezone: str = "Asia/Tehran"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def effective_health_port(self) -> int:
        return self.port or self.health_port

    @property
    def admin_id_set(self) -> set[int]:
        values: set[int] = set()
        for raw in self.admin_ids.split(","):
            raw = raw.strip()
            if raw.isdigit():
                values.add(int(raw))
        return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
