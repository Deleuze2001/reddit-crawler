from __future__ import annotations

from typing import Any

from .. import reddit
from ..crawlbase import CrawlbaseClient, CrawlbaseError
from ..settings_store import CrawlerSettings
from .base import ProviderError, ScrapeResult


class CrawlbaseProvider:
    name = "crawlbase"

    def __init__(self, settings: CrawlerSettings) -> None:
        self.settings = settings
        self.client = CrawlbaseClient(settings)

    @property
    def is_configured(self) -> bool:
        return self.settings.has_crawlbase_token

    def scrape(self, job: dict[str, Any]) -> ScrapeResult:
        if not self.is_configured:
            raise ProviderError("Add a Crawlbase normal or JavaScript token in Settings.")

        options = job.get("options") or {}
        limit = reddit.clamp_limit(job.get("post_limit"), self.settings.reddit_default_limit, self.settings.reddit_max_limit)
        comment_limit = reddit.clamp_limit(options.get("comment_limit"), 100, 500)
        include_comments = bool(job.get("include_comments"))
        stats = _empty_stats()
        metadata: dict[str, Any] = {}

        target_type = job["target_type"]
        if target_type == "subreddit":
            subreddit_name = reddit.clean_subreddit(job["target"])
            try:
                html_text, metadata = self._fetch_reddit_html(
                    reddit.old_subreddit_listing_url(subreddit_name, job.get("sort") or "hot"),
                    options,
                    stats,
                )
                posts = reddit.parse_old_reddit_listing(html_text, limit)
                metadata["source"] = "old_reddit_html"
                subreddits: list[dict[str, Any]] = []
            except CrawlbaseError as exc:
                metadata = {"error": str(exc), "fallback": "reddit_json"}
                body, metadata = self._fetch_reddit_json(reddit.subreddit_about_url(subreddit_name), options, stats)
                subreddit_about = reddit.parse_subreddit_about(body)
                subreddits = [subreddit_about] if subreddit_about else []
                if subreddit_about:
                    stats["subreddits"] += 1
                body, metadata = self._fetch_reddit_json(
                    reddit.subreddit_listing_url(subreddit_name, job.get("sort") or "hot", limit),
                    options,
                    stats,
                )
                posts = reddit.parse_listing_posts(body)

            comments: list[dict[str, Any]] = []
            if include_comments:
                comments, metadata = self._collect_comments_for_posts(posts, options, stats, comment_limit)
            stats["posts"] += len(posts)
            stats["comments"] += len(comments)
            return ScrapeResult(posts=posts, comments=comments, subreddits=subreddits, stats=stats, metadata=metadata)

        if target_type == "post":
            body, metadata = self._fetch_reddit_json(reddit.post_thread_url(job["target"], comment_limit), options, stats)
            posts, comments = reddit.parse_post_thread(body)
            stats["posts"] += len(posts)
            stats["comments"] += len(comments)
            return ScrapeResult(posts=posts, comments=comments, stats=stats, metadata=metadata)

        if target_type == "user":
            username = reddit.clean_username(job["target"])
            body, metadata = self._fetch_reddit_json(reddit.user_about_url(username), options, stats)
            user = reddit.parse_user_about(body)
            users = [user] if user else []
            if user:
                stats["users"] += 1

            body, metadata = self._fetch_reddit_json(reddit.user_submitted_url(username, limit), options, stats)
            posts = reddit.parse_listing_posts(body)
            comments: list[dict[str, Any]] = []
            if include_comments:
                comments, metadata = self._collect_comments_for_posts(posts, options, stats, comment_limit)
            stats["posts"] += len(posts)
            stats["comments"] += len(comments)
            return ScrapeResult(posts=posts, comments=comments, users=users, stats=stats, metadata=metadata)

        if target_type == "search":
            body, metadata = self._fetch_reddit_json(
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
            comments: list[dict[str, Any]] = []
            if include_comments:
                comments, metadata = self._collect_comments_for_posts(posts, options, stats, comment_limit)
            stats["posts"] += len(posts)
            stats["comments"] += len(comments)
            return ScrapeResult(posts=posts, comments=comments, stats=stats, metadata=metadata)

        raise ProviderError(f"Unsupported Crawlbase target type: {target_type}")

    def _fetch_reddit_json(
        self,
        url: str,
        options: dict[str, Any],
        stats: dict[str, Any],
    ) -> tuple[Any, dict[str, Any]]:
        result = self.client.fetch(
            url,
            use_js=bool(options.get("use_js")),
            autoparse=False,
            render_options=_render_options(options),
        )
        self.client.ensure_success(result)
        stats["requests"] += 1
        if not isinstance(result.body, (dict, list)):
            raise CrawlbaseError(f"Expected a JSON response from Reddit, got {type(result.body).__name__}.")
        return result.body, result.metadata()

    def _fetch_reddit_html(
        self,
        url: str,
        options: dict[str, Any],
        stats: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        result = self.client.fetch(
            url,
            use_js=bool(options.get("use_js")),
            autoparse=False,
            render_options=_render_options(options),
        )
        self.client.ensure_success(result)
        stats["requests"] += 1
        if not isinstance(result.body, str):
            raise CrawlbaseError(f"Expected an HTML response from Reddit, got {type(result.body).__name__}.")
        return result.body, result.metadata()

    def _collect_comments_for_posts(
        self,
        posts: list[dict[str, Any]],
        options: dict[str, Any],
        stats: dict[str, Any],
        comment_limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {}
        for post in posts:
            body, metadata = self._fetch_reddit_json(reddit.post_thread_url(post["id"], comment_limit), options, stats)
            thread_posts, thread_comments = reddit.parse_post_thread(body)
            if thread_posts:
                post.update(thread_posts[0])
            comments.extend(thread_comments)
        return comments, metadata


def _render_options(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "ajax_wait": True,
        "page_wait": options.get("page_wait") or 0,
        "scroll": bool(options.get("scroll")),
        "scroll_interval": options.get("scroll_interval") or 10,
    }


def _empty_stats() -> dict[str, Any]:
    return {
        "requests": 0,
        "posts": 0,
        "comments": 0,
        "subreddits": 0,
        "users": 0,
    }
