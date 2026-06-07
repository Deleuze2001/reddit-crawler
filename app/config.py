from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _string(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _optional_string(name: str, default: str = "") -> str | None:
    value = _string(name, default)
    return value or None


def _float(name: str, default: float) -> float:
    raw = _string(name, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    raw = _string(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    database_url: str
    crawlbase_normal_token: str | None
    crawlbase_js_token: str | None
    crawlbase_country: str | None
    crawlbase_device: str
    crawlbase_timeout_seconds: float
    crawlbase_rate_limit_seconds: float
    collector_poll_seconds: float
    reddit_default_limit: int
    reddit_max_limit: int
    web_app_title: str

    @property
    def has_crawlbase_token(self) -> bool:
        return bool(self.crawlbase_normal_token or self.crawlbase_js_token)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    max_limit = max(1, _int("REDDIT_MAX_LIMIT", 100))
    default_limit = min(max(1, _int("REDDIT_DEFAULT_LIMIT", 25)), max_limit)
    country = _optional_string("CRAWLBASE_COUNTRY", "US")

    return Settings(
        database_url=_string(
            "DATABASE_URL",
            "postgresql://reddit:reddit@localhost:5432/reddit_crawler",
        ),
        crawlbase_normal_token=_optional_string("CRAWLBASE_NORMAL_TOKEN"),
        crawlbase_js_token=_optional_string("CRAWLBASE_JS_TOKEN"),
        crawlbase_country=country.upper() if country else None,
        crawlbase_device=_string("CRAWLBASE_DEVICE", "desktop") or "desktop",
        crawlbase_timeout_seconds=max(30.0, _float("CRAWLBASE_TIMEOUT_SECONDS", 95.0)),
        crawlbase_rate_limit_seconds=max(0.0, _float("CRAWLBASE_RATE_LIMIT_SECONDS", 2.0)),
        collector_poll_seconds=max(1.0, _float("COLLECTOR_POLL_SECONDS", 5.0)),
        reddit_default_limit=default_limit,
        reddit_max_limit=max_limit,
        web_app_title=_string("WEB_APP_TITLE", "Reddit Crawlbase Collector"),
    )
