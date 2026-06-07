from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .settings_store import CrawlerSettings


CRAWLBASE_ENDPOINT = "https://api.crawlbase.com/"


class CrawlbaseError(RuntimeError):
    """Raised when Crawlbase cannot return a usable response."""


@dataclass
class CrawlbaseResult:
    target_url: str
    body: Any
    raw_body: str
    pc_status: int | None
    original_status: int | None
    final_url: str | None
    rid: str | None
    domain_complexity: str | None
    remaining: str | None
    used_js: bool
    headers: dict[str, str]

    @property
    def success(self) -> bool:
        if self.pc_status != 200:
            return False
        if self.original_status is not None and self.original_status >= 400:
            return False
        return True

    @property
    def empty_body(self) -> bool:
        return self.raw_body.strip() == "" or self.body in (None, "")

    def metadata(self) -> dict[str, Any]:
        return {
            "target_url": self.target_url,
            "final_url": self.final_url,
            "pc_status": self.pc_status,
            "original_status": self.original_status,
            "rid": self.rid,
            "domain_complexity": self.domain_complexity,
            "remaining": self.remaining,
            "used_js": self.used_js,
            "body_type": type(self.body).__name__,
        }


class CrawlbaseClient:
    def __init__(self, settings: CrawlerSettings) -> None:
        self.settings = settings
        self._last_request_at = 0.0

    def configure(self, settings: CrawlerSettings) -> None:
        self.settings = settings

    @property
    def has_token(self) -> bool:
        return self.settings.has_crawlbase_token

    def fetch(
        self,
        target_url: str,
        *,
        use_js: bool = False,
        autoparse: bool = False,
        render_options: dict[str, Any] | None = None,
    ) -> CrawlbaseResult:
        if not self.has_token:
            raise CrawlbaseError("Add a Crawlbase normal or JavaScript token in Settings.")

        first = self._fetch_once(
            target_url,
            use_js=use_js and bool(self.settings.crawlbase_js_token),
            autoparse=autoparse,
            render_options=render_options or {},
        )

        should_retry_js = (
            not first.used_js
            and bool(self.settings.crawlbase_js_token)
            and (first.pc_status == 525 or first.empty_body)
        )
        if should_retry_js:
            return self._fetch_once(
                target_url,
                use_js=True,
                autoparse=autoparse,
                render_options=render_options or {"ajax_wait": True},
            )

        return first

    def ensure_success(self, result: CrawlbaseResult) -> CrawlbaseResult:
        if result.success:
            return result
        raise CrawlbaseError(
            "Crawlbase request failed "
            f"(pc_status={result.pc_status}, original_status={result.original_status}, url={result.target_url})"
        )

    def _fetch_once(
        self,
        target_url: str,
        *,
        use_js: bool,
        autoparse: bool,
        render_options: dict[str, Any],
    ) -> CrawlbaseResult:
        self._respect_rate_limit()
        token = self.settings.crawlbase_js_token if use_js else self.settings.crawlbase_normal_token
        if not token:
            token = self.settings.crawlbase_js_token or self.settings.crawlbase_normal_token
            use_js = bool(token == self.settings.crawlbase_js_token)

        params: dict[str, Any] = {
            "token": token,
            "url": target_url,
            "format": "json",
            "request_headers": "accept:application/json,text/html;q=0.9,*/*;q=0.8|accept-language:en-US,en;q=0.9",
        }
        if self.settings.crawlbase_country:
            params["country"] = self.settings.crawlbase_country
        if self.settings.crawlbase_device:
            params["device"] = self.settings.crawlbase_device
        if autoparse:
            params["autoparse"] = "true"
        if use_js:
            params.update(_render_params(render_options))

        with httpx.Client(
            timeout=httpx.Timeout(self.settings.crawlbase_timeout_seconds),
            headers={"Accept-Encoding": "gzip"},
        ) as client:
            response = client.get(CRAWLBASE_ENDPOINT, params=params)
            response.raise_for_status()

        headers = {key.lower(): value for key, value in response.headers.items()}
        envelope = _json_or_none(response.text)
        if isinstance(envelope, dict) and ("body" in envelope or "pc_status" in envelope):
            body_value = envelope.get("body")
            raw_body = body_value if isinstance(body_value, str) else json.dumps(body_value or "")
            body = _decode_body(body_value)
            pc_status = _int_or_none(envelope.get("pc_status") or headers.get("pc_status"))
            original_status = _int_or_none(envelope.get("original_status") or headers.get("original_status"))
            final_url = envelope.get("url") or headers.get("url")
            rid = envelope.get("rid") or headers.get("rid")
            domain_complexity = envelope.get("domain_complexity") or headers.get("domain_complexity")
        else:
            raw_body = response.text
            body = _decode_body(response.text)
            pc_status = _int_or_none(headers.get("pc_status"))
            original_status = _int_or_none(headers.get("original_status"))
            final_url = headers.get("url")
            rid = headers.get("rid")
            domain_complexity = headers.get("domain_complexity")

        return CrawlbaseResult(
            target_url=target_url,
            body=body,
            raw_body=raw_body,
            pc_status=pc_status,
            original_status=original_status,
            final_url=final_url,
            rid=rid,
            domain_complexity=domain_complexity,
            remaining=headers.get("remaining"),
            used_js=use_js,
            headers=headers,
        )

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.settings.crawlbase_rate_limit_seconds - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()


def _render_params(options: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if options.get("ajax_wait", True):
        params["ajax_wait"] = "true"
    if options.get("scroll"):
        params["scroll"] = "true"
        if options.get("scroll_interval"):
            params["scroll_interval"] = int(options["scroll_interval"])
    if options.get("page_wait"):
        params["page_wait"] = int(options["page_wait"])
    if options.get("css_click_selector"):
        params["css_click_selector"] = str(options["css_click_selector"])
    return params


def _decode_body(value: Any) -> Any:
    if isinstance(value, str):
        parsed = _json_or_none(value)
        return parsed if parsed is not None else value
    return value


def _json_or_none(value: str) -> Any:
    text = value.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
