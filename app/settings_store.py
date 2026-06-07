from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import Connection


SECRET_KEYS = {"crawlbase_normal_token", "crawlbase_js_token"}
DEVICE_CHOICES = {"desktop", "tablet", "mobile"}

DEFAULT_VALUES: dict[str, str] = {
    "app_title": "Reddit Crawlbase Collector",
    "crawlbase_normal_token": "",
    "crawlbase_js_token": "",
    "crawlbase_country": "US",
    "crawlbase_device": "desktop",
    "crawlbase_timeout_seconds": "95",
    "crawlbase_rate_limit_seconds": "2.0",
    "collector_poll_seconds": "5",
    "reddit_default_limit": "25",
    "reddit_max_limit": "100",
}


@dataclass(frozen=True)
class CrawlerSettings:
    app_title: str
    crawlbase_normal_token: str | None
    crawlbase_js_token: str | None
    crawlbase_country: str | None
    crawlbase_device: str
    crawlbase_timeout_seconds: float
    crawlbase_rate_limit_seconds: float
    collector_poll_seconds: float
    reddit_default_limit: int
    reddit_max_limit: int

    @property
    def has_crawlbase_token(self) -> bool:
        return bool(self.crawlbase_normal_token or self.crawlbase_js_token)

    @property
    def has_normal_token(self) -> bool:
        return bool(self.crawlbase_normal_token)

    @property
    def has_js_token(self) -> bool:
        return bool(self.crawlbase_js_token)


def get_crawler_settings(conn: Connection) -> CrawlerSettings:
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    values = DEFAULT_VALUES | {row["key"]: row["value"] for row in rows}
    return settings_from_values(values)


def update_crawler_settings(conn: Connection, updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if key not in DEFAULT_VALUES:
            continue
        conn.execute(
            """
            INSERT INTO app_settings (key, value, is_secret, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                is_secret = EXCLUDED.is_secret,
                updated_at = now()
            """,
            (key, str(value), key in SECRET_KEYS),
        )


def settings_from_values(values: dict[str, Any]) -> CrawlerSettings:
    max_limit = _bounded_int(values.get("reddit_max_limit"), 100, minimum=1, maximum=500)
    default_limit = _bounded_int(values.get("reddit_default_limit"), 25, minimum=1, maximum=max_limit)
    country = _country_or_none(values.get("crawlbase_country"))
    device = str(values.get("crawlbase_device") or "desktop").strip().lower()
    if device not in DEVICE_CHOICES:
        device = "desktop"

    return CrawlerSettings(
        app_title=str(values.get("app_title") or DEFAULT_VALUES["app_title"]).strip()
        or DEFAULT_VALUES["app_title"],
        crawlbase_normal_token=_secret_or_none(values.get("crawlbase_normal_token")),
        crawlbase_js_token=_secret_or_none(values.get("crawlbase_js_token")),
        crawlbase_country=country,
        crawlbase_device=device,
        crawlbase_timeout_seconds=_bounded_float(
            values.get("crawlbase_timeout_seconds"),
            95.0,
            minimum=30.0,
            maximum=300.0,
        ),
        crawlbase_rate_limit_seconds=_bounded_float(
            values.get("crawlbase_rate_limit_seconds"),
            2.0,
            minimum=0.0,
            maximum=60.0,
        ),
        collector_poll_seconds=_bounded_float(
            values.get("collector_poll_seconds"),
            5.0,
            minimum=1.0,
            maximum=300.0,
        ),
        reddit_default_limit=default_limit,
        reddit_max_limit=max_limit,
    )


def public_settings(settings: CrawlerSettings) -> dict[str, Any]:
    return {
        "app_title": settings.app_title,
        "crawlbase_normal_token_saved": settings.has_normal_token,
        "crawlbase_js_token_saved": settings.has_js_token,
        "crawlbase_country": settings.crawlbase_country or "",
        "crawlbase_device": settings.crawlbase_device,
        "crawlbase_timeout_seconds": settings.crawlbase_timeout_seconds,
        "crawlbase_rate_limit_seconds": settings.crawlbase_rate_limit_seconds,
        "collector_poll_seconds": settings.collector_poll_seconds,
        "reddit_default_limit": settings.reddit_default_limit,
        "reddit_max_limit": settings.reddit_max_limit,
    }


def _secret_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _country_or_none(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if len(text) == 2 and text.isalpha():
        return text
    return "US"


def _bounded_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _bounded_float(value: Any, default: float, *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)
