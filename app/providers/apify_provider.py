from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from apify_client import ApifyClient

from .. import reddit
from ..settings_store import CrawlerSettings
from .base import ProviderError, ScrapeResult


APIFY_REDDIT_PAGE_FUNCTION = r"""
async function pageFunction(context) {
    const { request, customData } = context;
    const scrapeType = request.userData.scrapeType || customData.scrapeType;
    const postLimit = Number(customData.postLimit || 25);
    const commentLimit = Number(customData.commentLimit || 100);

    const text = (node) => node ? node.textContent.replace(/\s+/g, ' ').trim() : null;
    const intAttr = (node, name) => {
        const raw = node && node.getAttribute(name);
        if (!raw) return null;
        const parsed = Number.parseInt(raw, 10);
        return Number.isFinite(parsed) ? parsed : null;
    };
    const boolAttr = (node, name) => {
        const raw = node && node.getAttribute(name);
        if (raw === 'true') return true;
        if (raw === 'false') return false;
        return null;
    };
    const absolute = (value) => {
        if (!value) return null;
        try {
            return new URL(value, 'https://www.reddit.com').toString();
        } catch {
            return value;
        }
    };
    const createdAt = (node) => {
        const rawMillis = intAttr(node, 'data-timestamp');
        if (rawMillis) return new Date(rawMillis).toISOString();
        const time = node ? node.querySelector('time[datetime]') : null;
        return time ? time.getAttribute('datetime') : null;
    };
    const postFromThing = (node) => {
        const fullname = node.getAttribute('data-fullname') || '';
        const titleNode = node.querySelector('a.title');
        const permalink = absolute(node.getAttribute('data-permalink') || (titleNode && titleNode.getAttribute('href')));
        return {
            id: fullname.replace(/^t3_/, ''),
            fullname,
            subreddit: node.getAttribute('data-subreddit') || null,
            title: text(titleNode),
            author: node.getAttribute('data-author') || null,
            selftext: text(node.querySelector('.expando .usertext-body, .usertext-body .md')) || '',
            url: absolute(node.getAttribute('data-url') || (titleNode && titleNode.getAttribute('href'))) || permalink,
            permalink,
            thumbnail: null,
            mediaUrl: null,
            createdAt: createdAt(node),
            score: intAttr(node, 'data-score'),
            upvoteRatio: null,
            numComments: intAttr(node, 'data-comments-count'),
            isSelf: (node.getAttribute('data-domain') || '').startsWith('self.'),
            over18: boolAttr(node, 'data-nsfw'),
            flairText: node.querySelector('.linkflairlabel') ? node.querySelector('.linkflairlabel').getAttribute('title') : null,
            raw: {
                source: 'apify_web_scraper_old_reddit',
                attrs: Object.fromEntries([...node.attributes].map((attr) => [attr.name, attr.value])),
            },
        };
    };
    const commentFromThing = (node, postId) => {
        const fullname = node.getAttribute('data-fullname') || '';
        const id = fullname.replace(/^t1_/, '');
        const scoreNode = node.querySelector('.score.unvoted, .score.likes, .score.dislikes');
        const permalinkNode = node.querySelector('a.bylink, a[data-event-action="permalink"]');
        return {
            id,
            fullname,
            postId,
            parentId: node.getAttribute('data-parent-fullname') || null,
            author: node.getAttribute('data-author') || text(node.querySelector('.author')),
            body: text(node.querySelector('.usertext-body .md')) || '',
            score: scoreNode ? Number.parseInt(scoreNode.getAttribute('title') || scoreNode.textContent, 10) || null : null,
            createdAt: createdAt(node),
            permalink: absolute(permalinkNode && permalinkNode.getAttribute('href')),
            raw: {
                source: 'apify_web_scraper_old_reddit',
                attrs: Object.fromEntries([...node.attributes].map((attr) => [attr.name, attr.value])),
            },
        };
    };

    const postNodes = [...document.querySelectorAll('div.thing.link[data-fullname^="t3_"]')];
    const posts = postNodes.slice(0, scrapeType === 'subreddit' ? postLimit : 1).map(postFromThing);
    const postId = posts[0] ? posts[0].id : null;
    const comments = scrapeType === 'post'
        ? [...document.querySelectorAll('div.thing.comment[data-fullname^="t1_"]')]
            .slice(0, commentLimit)
            .map((node) => commentFromThing(node, postId))
            .filter((comment) => comment.id && comment.body)
        : [];

    return {
        provider: 'apify',
        actor: customData.actorId || 'apify/web-scraper',
        source: 'old_reddit_html',
        scrapeType,
        url: request.url,
        loadedUrl: window.location.href,
        title: document.title,
        posts,
        comments,
        counts: {
            posts: posts.length,
            comments: comments.length,
        },
    };
}
"""


APIFY_CHEERIO_PAGE_FUNCTION = r"""
async function pageFunction(context) {
    const { request, response, $, customData } = context;
    const scrapeType = request.userData.scrapeType || customData.scrapeType;
    const postLimit = Number(customData.postLimit || 25);
    const commentLimit = Number(customData.commentLimit || 100);

    const cleanText = (value) => String(value || '').replace(/\s+/g, ' ').trim() || null;
    const text = ($node) => cleanText($node && $node.length ? $node.text() : '');
    const numeric = (value) => {
        const match = String(value || '').replace(/,/g, '').match(/-?\d+/);
        if (!match) return null;
        const parsed = Number.parseInt(match[0], 10);
        return Number.isFinite(parsed) ? parsed : null;
    };
    const boolAttr = ($node, name) => {
        const raw = $node.attr(name);
        if (raw === 'true') return true;
        if (raw === 'false') return false;
        return null;
    };
    const absolute = (value) => {
        if (!value) return null;
        try {
            return new URL(value, 'https://www.reddit.com').toString();
        } catch {
            return value;
        }
    };
    const attrs = ($node) => Object.assign({}, $node.attr() || {});
    const createdAt = ($node) => {
        const millis = numeric($node.attr('data-timestamp'));
        if (millis) return new Date(millis).toISOString();
        const datetime = $node.find('time[datetime]').first().attr('datetime');
        return datetime || null;
    };
    const scoreFrom = ($node) => {
        const score = numeric($node.attr('data-score'));
        if (score !== null) return score;
        const $score = $node.find('.score.unvoted, .score.likes, .score.dislikes').first();
        return numeric($score.attr('title') || $score.text());
    };
    const postFromThing = (element) => {
        const $node = $(element);
        const fullname = $node.attr('data-fullname') || '';
        const $title = $node.find('a.title').first();
        const permalink = absolute($node.attr('data-permalink') || $title.attr('href'));
        const url = absolute($node.attr('data-url') || $title.attr('href')) || permalink;

        return {
            id: fullname.replace(/^t3_/, ''),
            fullname,
            subreddit: $node.attr('data-subreddit') || null,
            title: text($title),
            author: $node.attr('data-author') || null,
            selftext: text($node.find('.expando .usertext-body .md, .usertext-body .md').first()) || '',
            url,
            permalink,
            thumbnail: null,
            mediaUrl: null,
            createdAt: createdAt($node),
            score: scoreFrom($node),
            upvoteRatio: null,
            numComments: numeric($node.attr('data-comments-count') || $node.find('a.comments').first().text()),
            isSelf: ($node.attr('data-domain') || '').startsWith('self.'),
            over18: boolAttr($node, 'data-nsfw'),
            flairText: $node.find('.linkflairlabel').first().attr('title') || text($node.find('.linkflairlabel').first()),
            raw: {
                source: 'apify_cheerio_old_reddit',
                attrs: attrs($node),
            },
        };
    };
    const commentFromThing = (element, postId) => {
        const $node = $(element);
        const fullname = $node.attr('data-fullname') || '';
        const $score = $node.find('.score.unvoted, .score.likes, .score.dislikes').first();
        const $permalink = $node.find('a.bylink, a[data-event-action="permalink"]').first();

        return {
            id: fullname.replace(/^t1_/, ''),
            fullname,
            postId,
            parentId: $node.attr('data-parent-fullname') || null,
            author: $node.attr('data-author') || text($node.find('.author').first()),
            body: text($node.find('.usertext-body .md').first()) || '',
            score: numeric($score.attr('title') || $score.text()),
            createdAt: createdAt($node),
            permalink: absolute($permalink.attr('href')),
            raw: {
                source: 'apify_cheerio_old_reddit',
                attrs: attrs($node),
            },
        };
    };

    const postNodes = $('div.thing.link[data-fullname^="t3_"]').toArray();
    const posts = postNodes
        .slice(0, scrapeType === 'subreddit' ? postLimit : 1)
        .map(postFromThing)
        .filter((post) => post.id && post.title);
    const postId = posts[0] ? posts[0].id : null;
    const comments = scrapeType === 'post'
        ? $('div.thing.comment[data-fullname^="t1_"]')
            .toArray()
            .slice(0, commentLimit)
            .map((element) => commentFromThing(element, postId))
            .filter((comment) => comment.id && comment.body)
        : [];

    return {
        provider: 'apify',
        actor: customData.actorId || 'apify/cheerio-scraper',
        source: 'old_reddit_html',
        scrapeType,
        url: request.url,
        loadedUrl: (response && response.url) || request.loadedUrl || request.url,
        title: text($('title').first()),
        posts,
        comments,
        counts: {
            posts: posts.length,
            comments: comments.length,
        },
    };
}
"""


class ApifyProvider:
    name = "apify"

    def __init__(self, settings: CrawlerSettings) -> None:
        self.settings = settings

    @property
    def is_configured(self) -> bool:
        return self.settings.has_apify_token

    def scrape(self, job: dict[str, Any]) -> ScrapeResult:
        if not self.settings.apify_token:
            raise ProviderError("Add an Apify API token in Settings.")
        target_type = job["target_type"]
        if target_type not in {"subreddit", "post"}:
            raise ProviderError("The Apify provider currently supports subreddit and post jobs.")

        options = job.get("options") or {}
        limit = reddit.clamp_limit(job.get("post_limit"), self.settings.reddit_default_limit, self.settings.reddit_max_limit)
        comment_limit = reddit.clamp_limit(options.get("comment_limit"), 100, 500)
        url = _target_url(job, target_type)
        run_input = self.build_run_input(url, target_type, limit, comment_limit)

        client = ApifyClient(self.settings.apify_token)
        try:
            run = client.actor(self.settings.apify_actor_id).call(
                run_input=run_input,
                timeout_secs=self.settings.apify_run_timeout_seconds,
                max_items=1,
                logger=None,
            )
        except Exception as exc:  # noqa: BLE001 - provider SDK errors need a stable app error.
            raise ProviderError(f"Apify actor run failed: {_sanitize_error(exc)}") from exc

        if not run or not run.get("defaultDatasetId"):
            raise ProviderError("Apify actor run did not return a default dataset.")

        try:
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items(limit=1, clean=True))
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Apify dataset read failed: {_sanitize_error(exc)}") from exc

        result = self.result_from_items(items)
        result.metadata.update(
            {
                "provider": self.name,
                "actor_id": self.settings.apify_actor_id,
                "run_id": run.get("id"),
                "default_dataset_id": run.get("defaultDatasetId"),
                "status": run.get("status"),
                "target_url": url,
                "dataset_items": len(items),
            }
        )
        result.stats["requests"] = 1
        return result

    def build_run_input(self, url: str, target_type: str, post_limit: int, comment_limit: int) -> dict[str, Any]:
        if _is_cheerio_actor(self.settings.apify_actor_id):
            return self._build_cheerio_run_input(url, target_type, post_limit, comment_limit)
        return self._build_web_scraper_run_input(url, target_type, post_limit, comment_limit)

    def _build_cheerio_run_input(
        self,
        url: str,
        target_type: str,
        post_limit: int,
        comment_limit: int,
    ) -> dict[str, Any]:
        proxy_config = self._proxy_configuration()

        return {
            "startUrls": [{"url": url, "userData": {"scrapeType": target_type}}],
            "linkSelector": "",
            "pageFunction": APIFY_CHEERIO_PAGE_FUNCTION,
            "proxyConfiguration": proxy_config,
            "proxyRotation": "RECOMMENDED",
            "maxRequestRetries": self.settings.apify_max_request_retries,
            "maxPagesPerCrawl": 1,
            "maxResultsPerCrawl": 1,
            "maxCrawlingDepth": 0,
            "maxConcurrency": 1,
            "pageLoadTimeoutSecs": self.settings.apify_page_load_timeout_seconds,
            "pageFunctionTimeoutSecs": self.settings.apify_page_function_timeout_seconds,
            "customData": {
                "actorId": self.settings.apify_actor_id,
                "scrapeType": target_type,
                "postLimit": post_limit,
                "commentLimit": comment_limit,
            },
        }

    def _build_web_scraper_run_input(
        self,
        url: str,
        target_type: str,
        post_limit: int,
        comment_limit: int,
    ) -> dict[str, Any]:
        proxy_config = self._proxy_configuration()

        return {
            "runMode": "PRODUCTION",
            "startUrls": [{"url": url, "userData": {"scrapeType": target_type}}],
            "linkSelector": "",
            "pageFunction": APIFY_REDDIT_PAGE_FUNCTION,
            "injectJQuery": False,
            "proxyConfiguration": proxy_config,
            "proxyRotation": "RECOMMENDED",
            "useChrome": self.settings.apify_use_chrome,
            "headless": True,
            "downloadMedia": False,
            "downloadCss": True,
            "maxRequestRetries": self.settings.apify_max_request_retries,
            "maxPagesPerCrawl": 1,
            "maxResultsPerCrawl": 1,
            "maxCrawlingDepth": 0,
            "maxConcurrency": 1,
            "pageLoadTimeoutSecs": self.settings.apify_page_load_timeout_seconds,
            "pageFunctionTimeoutSecs": self.settings.apify_page_function_timeout_seconds,
            "waitUntil": ["domcontentloaded"],
            "maxScrollHeightPixels": self.settings.apify_max_scroll_height_pixels,
            "customData": {
                "actorId": self.settings.apify_actor_id,
                "scrapeType": target_type,
                "postLimit": post_limit,
                "commentLimit": comment_limit,
            },
        }

    def _proxy_configuration(self) -> dict[str, Any]:
        proxy_config: dict[str, Any] = {"useApifyProxy": self.settings.apify_use_apify_proxy}
        if self.settings.apify_proxy_group:
            proxy_config["apifyProxyGroups"] = [self.settings.apify_proxy_group]
            proxy_config["groups"] = [self.settings.apify_proxy_group]
        if self.settings.apify_proxy_country:
            proxy_config["apifyProxyCountry"] = self.settings.apify_proxy_country
            proxy_config["countryCode"] = self.settings.apify_proxy_country
        return proxy_config

    def result_from_items(self, items: list[dict[str, Any]]) -> ScrapeResult:
        stats = _empty_stats()
        posts: list[dict[str, Any]] = []
        comments: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {"provider": self.name, "source": "apify_dataset"}

        for item in items:
            item_posts = [_normalize_post(post) for post in item.get("posts", []) if isinstance(post, dict)]
            posts.extend(post for post in item_posts if post.get("id"))
            item_comments = [_normalize_comment(comment) for comment in item.get("comments", []) if isinstance(comment, dict)]
            comments.extend(comment for comment in item_comments if comment.get("id"))
            metadata.update(
                {
                    "loaded_url": item.get("loadedUrl"),
                    "scrape_type": item.get("scrapeType"),
                    "page_title": item.get("title"),
                    "source": item.get("source") or metadata["source"],
                }
            )

        stats["posts"] = len(posts)
        stats["comments"] = len(comments)
        return ScrapeResult(posts=posts, comments=comments, stats=stats, metadata=metadata)


def _target_url(job: dict[str, Any], target_type: str) -> str:
    if target_type == "subreddit":
        return reddit.old_subreddit_listing_url(job["target"], job.get("sort") or "hot")
    if target_type == "post":
        return reddit.old_post_thread_url(job["target"])
    raise ProviderError(f"Unsupported Apify target type: {target_type}")


def _normalize_post(post: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": post.get("id"),
        "fullname": post.get("fullname"),
        "subreddit": post.get("subreddit"),
        "title": post.get("title"),
        "author": post.get("author"),
        "selftext": post.get("selftext") or "",
        "url": post.get("url"),
        "permalink": post.get("permalink"),
        "thumbnail": post.get("thumbnail"),
        "media_url": post.get("mediaUrl") or post.get("media_url"),
        "created_at": _parse_datetime(post.get("createdAt") or post.get("created_at")),
        "score": _int_or_none(post.get("score")),
        "upvote_ratio": _float_or_none(post.get("upvoteRatio") or post.get("upvote_ratio")),
        "num_comments": _int_or_none(post.get("numComments") or post.get("num_comments")),
        "is_self": post.get("isSelf") if "isSelf" in post else post.get("is_self"),
        "over18": post.get("over18"),
        "flair_text": post.get("flairText") or post.get("flair_text"),
        "raw": post,
    }


def _normalize_comment(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": comment.get("id"),
        "fullname": comment.get("fullname"),
        "post_id": comment.get("postId") or comment.get("post_id"),
        "parent_id": comment.get("parentId") or comment.get("parent_id"),
        "author": comment.get("author"),
        "body": comment.get("body") or "",
        "score": _int_or_none(comment.get("score")),
        "created_at": _parse_datetime(comment.get("createdAt") or comment.get("created_at")),
        "permalink": comment.get("permalink"),
        "raw": comment,
    }


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _empty_stats() -> dict[str, Any]:
    return {
        "requests": 0,
        "posts": 0,
        "comments": 0,
        "subreddits": 0,
        "users": 0,
    }


def _sanitize_error(exc: Exception) -> str:
    message = re.sub(r"apify_api_[A-Za-z0-9_-]+", "apify_api_[REDACTED]", str(exc))
    token = "token="
    if token in message:
        return message.split(token, 1)[0] + "token=[REDACTED]"
    return message


def _is_cheerio_actor(actor_id: str) -> bool:
    return "cheerio-scraper" in actor_id.strip().lower()


ApifyWebScraperProvider = ApifyProvider
