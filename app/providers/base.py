from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """Raised when a scraper provider cannot complete a scrape."""


@dataclass
class ScrapeResult:
    posts: list[dict[str, Any]] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)
    subreddits: list[dict[str, Any]] = field(default_factory=list)
    users: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ScraperProvider(Protocol):
    name: str

    @property
    def is_configured(self) -> bool:
        ...

    def scrape(self, job: dict[str, Any]) -> ScrapeResult:
        ...
