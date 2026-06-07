from __future__ import annotations

import time
import traceback
from typing import Any

from . import database, reddit, repository
from .config import Settings, get_settings
from .crawlbase import CrawlbaseClient, CrawlbaseError


def main() -> None:
    settings = get_settings()
    database.run_migrations(settings)
    client = CrawlbaseClient(settings)

    print("collector ready", flush=True)
    while True:
        if not client.has_token:
            print("collector waiting for CRAWLBASE_NORMAL_TOKEN or CRAWLBASE_JS_TOKEN", flush=True)
            time.sleep(max(30.0, settings.collector_poll_seconds))
            continue

        job = repository.claim_next_job(settings)
        if job is None:
            time.sleep(settings.collector_poll_seconds)
            continue

        print(f"collector claimed job {job['id']} ({job['target_type']} {job['target']})", flush=True)
        with database.connection(settings) as conn:
            try:
                stats, last_response = process_job(conn, job, client, settings)
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
    job: dict[str, Any],
    client: CrawlbaseClient,
    settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any]]:
    options = job.get("options") or {}
    limit = reddit.clamp_limit(job.get("post_limit"), settings.reddit_default_limit, settings.reddit_max_limit)
    comment_limit = reddit.clamp_limit(options.get("comment_limit"), 100, 500)
    include_comments = bool(job.get("include_comments"))

    stats: dict[str, Any] = {
        "requests": 0,
        "posts": 0,
        "comments": 0,
        "subreddits": 0,
        "users": 0,
    }
    last_response: dict[str, Any] = {}

    target_type = job["target_type"]
    if target_type == "subreddit":
        subreddit_name = reddit.clean_subreddit(job["target"])
        body, last_response = _fetch_reddit_json(
            client,
            reddit.subreddit_about_url(subreddit_name),
            options,
            stats,
        )
        subreddit_about = reddit.parse_subreddit_about(body)
        if subreddit_about:
            repository.save_subreddit(conn, subreddit_about)
            stats["subreddits"] += 1

        body, last_response = _fetch_reddit_json(
            client,
            reddit.subreddit_listing_url(subreddit_name, job.get("sort") or "hot", limit),
            options,
            stats,
        )
        posts = reddit.parse_listing_posts(body)
        _save_posts(conn, posts, str(job["id"]), stats)
        if include_comments:
            last_response = _collect_comments_for_posts(conn, posts, str(job["id"]), client, options, stats, comment_limit)

    elif target_type == "post":
        body, last_response = _fetch_reddit_json(
            client,
            reddit.post_thread_url(job["target"], comment_limit),
            options,
            stats,
        )
        posts, comments = reddit.parse_post_thread(body)
        _save_posts(conn, posts, str(job["id"]), stats)
        _save_comments(conn, comments, str(job["id"]), stats)

    elif target_type == "user":
        username = reddit.clean_username(job["target"])
        body, last_response = _fetch_reddit_json(client, reddit.user_about_url(username), options, stats)
        user = reddit.parse_user_about(body)
        if user:
            repository.save_user(conn, user)
            stats["users"] += 1

        body, last_response = _fetch_reddit_json(client, reddit.user_submitted_url(username, limit), options, stats)
        posts = reddit.parse_listing_posts(body)
        _save_posts(conn, posts, str(job["id"]), stats)
        if include_comments:
            last_response = _collect_comments_for_posts(conn, posts, str(job["id"]), client, options, stats, comment_limit)

    elif target_type == "search":
        body, last_response = _fetch_reddit_json(
            client,
            reddit.search_url(
                job["target"],
                job.get("sort") or "relevance",
                limit,
                subreddit=options.get("subreddit") or None,
            ),
            options,
            stats,
        )
        posts = reddit.parse_listing_posts(body)
        _save_posts(conn, posts, str(job["id"]), stats)
        if include_comments:
            last_response = _collect_comments_for_posts(conn, posts, str(job["id"]), client, options, stats, comment_limit)

    else:
        raise ValueError(f"Unsupported target_type: {target_type}")

    return stats, last_response


def _fetch_reddit_json(
    client: CrawlbaseClient,
    url: str,
    options: dict[str, Any],
    stats: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    result = client.fetch(
        url,
        use_js=bool(options.get("use_js")),
        autoparse=False,
        render_options={
            "ajax_wait": True,
            "page_wait": options.get("page_wait") or 0,
            "scroll": bool(options.get("scroll")),
            "scroll_interval": options.get("scroll_interval") or 10,
        },
    )
    client.ensure_success(result)
    stats["requests"] += 1
    if not isinstance(result.body, (dict, list)):
        raise CrawlbaseError(f"Expected a JSON response from Reddit, got {type(result.body).__name__}.")
    return result.body, result.metadata()


def _collect_comments_for_posts(
    conn,
    posts: list[dict[str, Any]],
    job_id: str,
    client: CrawlbaseClient,
    options: dict[str, Any],
    stats: dict[str, Any],
    comment_limit: int,
) -> dict[str, Any]:
    last_response: dict[str, Any] = {}
    for post in posts:
        body, last_response = _fetch_reddit_json(
            client,
            reddit.post_thread_url(post["id"], comment_limit),
            options,
            stats,
        )
        thread_posts, comments = reddit.parse_post_thread(body)
        _save_posts(conn, thread_posts, job_id, stats, count_new=False)
        _save_comments(conn, comments, job_id, stats)
    return last_response


def _save_posts(
    conn,
    posts: list[dict[str, Any]],
    job_id: str,
    stats: dict[str, Any],
    *,
    count_new: bool = True,
) -> None:
    for post in posts:
        repository.save_post(conn, post, job_id)
    if count_new:
        stats["posts"] += len(posts)


def _save_comments(conn, comments: list[dict[str, Any]], job_id: str, stats: dict[str, Any]) -> None:
    for comment in comments:
        repository.save_comment(conn, comment, job_id)
    stats["comments"] += len(comments)


if __name__ == "__main__":
    main()
