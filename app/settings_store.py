from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import Connection


PROVIDER_CHOICES = {"crawlbase", "apify"}
SECRET_KEYS = {"crawlbase_normal_token", "crawlbase_js_token", "apify_token"}
DEVICE_CHOICES = {"desktop", "tablet", "mobile"}

DEFAULT_VALUES: dict[str, str] = {
    "app_title": "Reddit Scraper Collector",
    "default_scraper_provider": "crawlbase",
    "crawlbase_normal_token": "",
    "crawlbase_js_token": "",
    "crawlbase_country": "US",
    "crawlbase_device": "desktop",
    "crawlbase_timeout_seconds": "95",
    "crawlbase_rate_limit_seconds": "2.0",
    "collector_poll_seconds": "5",
    "reddit_default_limit": "25",
    "reddit_max_limit": "100",
    "apify_token": "",
    "apify_actor_id": "apify/web-scraper",
    "apify_run_timeout_seconds": "300",
    "apify_page_load_timeout_seconds": "90",
    "apify_page_function_timeout_seconds": "60",
    "apify_max_request_retries": "2",
    "apify_max_scroll_height_pixels": "8000",
    "apify_proxy_group": "RESIDENTIAL",
    "apify_proxy_country": "US",
    "apify_use_apify_proxy": "true",
    "apify_use_chrome": "true",
}


@dataclass(frozen=True)
class CrawlerSettings:
    app_title: str
    default_scraper_provider: str
    crawlbase_normal_token: str | None
    crawlbase_js_token: str | None
    crawlbase_country: str | None
    crawlbase_device: str
    crawlbase_timeout_seconds: float
    crawlbase_rate_limit_seconds: float
    collector_poll_seconds: float
    reddit_default_limit: int
    reddit_max_limit: int
    apify_token: str | None
    apify_actor_id: str
    apify_run_timeout_seconds: int
    apify_page_load_timeout_seconds: int
    apify_page_function_timeout_seconds: int
    apify_max_request_retries: int
    apify_max_scroll_height_pixels: int
    apify_proxy_group: str | None
    apify_proxy_country: str | None
    apify_use_apify_proxy: bool
    apify_use_chrome: bool

    @property
    def has_crawlbase_token(self) -> bool:
        return bool(self.crawlbase_normal_token or self.crawlbase_js_token)

    @property
    def has_normal_token(self) -> bool:
        return bool(self.crawlbase_normal_token)

    @property
    def has_js_token(self) -> bool:
        return bool(self.crawlbase_js_token)

    @property
    def has_apify_token(self) -> bool:
        return bool(self.apify_token)

    def has_provider_credentials(self, provider: str) -> bool:
        if provider == "crawlbase":
            return self.has_crawlbase_token
        if provider == "apify":
            return self.has_apify_token
        return False

    @property
    def has_any_provider_credentials(self) -> bool:
        return self.has_crawlbase_token or self.has_apify_token


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
    provider = str(values.get("default_scraper_provider") or "crawlbase").strip().lower()
    if provider not in PROVIDER_CHOICES:
        provider = "crawlbase"
    country = _country_or_none(values.get("crawlbase_country"))
    apify_proxy_group = _text_or_none(values.get("apify_proxy_group"))
    apify_country = _country_or_none(values.get("apify_proxy_country"))
    device = str(values.get("crawlbase_device") or "desktop").strip().lower()
    if device not in DEVICE_CHOICES:
        device = "desktop"

    return CrawlerSettings(
        app_title=str(values.get("app_title") or DEFAULT_VALUES["app_title"]).strip()
        or DEFAULT_VALUES["app_title"],
        default_scraper_provider=provider,
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
        apify_token=_secret_or_none(values.get("apify_token")),
        apify_actor_id=str(values.get("apify_actor_id") or DEFAULT_VALUES["apify_actor_id"]).strip()
        or DEFAULT_VALUES["apify_actor_id"],
        apify_run_timeout_seconds=_bounded_int(
            values.get("apify_run_timeout_seconds"),
            300,
            minimum=30,
            maximum=1800,
        ),
        apify_page_load_timeout_seconds=_bounded_int(
            values.get("apify_page_load_timeout_seconds"),
            90,
            minimum=10,
            maximum=300,
        ),
        apify_page_function_timeout_seconds=_bounded_int(
            values.get("apify_page_function_timeout_seconds"),
            60,
            minimum=5,
            maximum=300,
        ),
        apify_max_request_retries=_bounded_int(
            values.get("apify_max_request_retries"),
            2,
            minimum=0,
            maximum=10,
        ),
        apify_max_scroll_height_pixels=_bounded_int(
            values.get("apify_max_scroll_height_pixels"),
            8000,
            minimum=0,
            maximum=100000,
        ),
        apify_proxy_group=apify_proxy_group,
        apify_proxy_country=apify_country,
        apify_use_apify_proxy=_bool(values.get("apify_use_apify_proxy"), True),
        apify_use_chrome=_bool(values.get("apify_use_chrome"), True),
    )


def public_settings(settings: CrawlerSettings) -> dict[str, Any]:
    return {
        "app_title": settings.app_title,
        "default_scraper_provider": settings.default_scraper_provider,
        "crawlbase_normal_token_saved": settings.has_normal_token,
        "crawlbase_js_token_saved": settings.has_js_token,
        "crawlbase_country": settings.crawlbase_country or "",
        "crawlbase_device": settings.crawlbase_device,
        "crawlbase_timeout_seconds": settings.crawlbase_timeout_seconds,
        "crawlbase_rate_limit_seconds": settings.crawlbase_rate_limit_seconds,
        "collector_poll_seconds": settings.collector_poll_seconds,
        "reddit_default_limit": settings.reddit_default_limit,
        "reddit_max_limit": settings.reddit_max_limit,
        "apify_token_saved": settings.has_apify_token,
        "apify_actor_id": settings.apify_actor_id,
        "apify_run_timeout_seconds": settings.apify_run_timeout_seconds,
        "apify_page_load_timeout_seconds": settings.apify_page_load_timeout_seconds,
        "apify_page_function_timeout_seconds": settings.apify_page_function_timeout_seconds,
        "apify_max_request_retries": settings.apify_max_request_retries,
        "apify_max_scroll_height_pixels": settings.apify_max_scroll_height_pixels,
        "apify_proxy_group": settings.apify_proxy_group or "",
        "apify_proxy_country": settings.apify_proxy_country or "",
        "apify_use_apify_proxy": settings.apify_use_apify_proxy,
        "apify_use_chrome": settings.apify_use_chrome,
    }


def _secret_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _text_or_none(value: Any) -> str | None:
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


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default
