from __future__ import annotations

import time
import traceback

from . import database, repository, settings_store
from .config import get_settings
from .providers import ApifyProvider, CrawlbaseProvider, ProviderError, ScrapeResult
from .settings_store import CrawlerSettings


def main() -> None:
    settings = get_settings()
    database.run_migrations(settings)

    print("collector ready", flush=True)
    while True:
        with database.connection(settings) as conn:
            crawler_settings = settings_store.get_crawler_settings(conn)

        if not crawler_settings.has_any_provider_credentials:
            print("collector waiting for scraper provider credentials saved from the web UI", flush=True)
            time.sleep(max(30.0, crawler_settings.collector_poll_seconds))
            continue

        job = repository.claim_next_job(settings)
        if job is None:
            time.sleep(crawler_settings.collector_poll_seconds)
            continue

        print(f"collector claimed job {job['id']} ({job['target_type']} {job['target']})", flush=True)
        with database.connection(settings) as conn:
            try:
                stats, last_response = process_job(conn, job, crawler_settings)
                repository.complete_job(conn, str(job["id"]), stats=stats, last_response=last_response)
                print(f"collector completed job {job['id']} stats={stats}", flush=True)
            except Exception as exc:  # noqa: BLE001 - job errors need to be captured in the database.
                traceback.print_exc()
                repository.fail_job(
                    conn,
                    str(job["id"]),
                    error=str(exc),
                    stats={"requests": 0},
                )


def process_job(
    conn,
    job: dict,
    settings: CrawlerSettings,
) -> tuple[dict, dict]:
    provider = _build_provider(job.get("provider") or settings.default_scraper_provider, settings)
    result = provider.scrape(job)
    _save_result(conn, result, str(job["id"]))
    return result.stats, result.metadata


def _build_provider(provider_name: str, settings: CrawlerSettings):
    if provider_name == "crawlbase":
        return CrawlbaseProvider(settings)
    if provider_name == "apify":
        return ApifyProvider(settings)
    raise ProviderError(f"Unknown scraper provider: {provider_name}")


def _save_result(conn, result: ScrapeResult, job_id: str) -> None:
    for subreddit in result.subreddits:
        repository.save_subreddit(conn, subreddit)
    for user in result.users:
        repository.save_user(conn, user)
    _save_posts(conn, result.posts, job_id)
    _save_comments(conn, result.comments, job_id)


def _save_posts(
    conn,
    posts: list[dict],
    job_id: str,
) -> None:
    for post in posts:
        repository.save_post(conn, post, job_id)


def _save_comments(conn, comments: list[dict], job_id: str) -> None:
    for comment in comments:
        repository.save_comment(conn, comment, job_id)


if __name__ == "__main__":
    main()
