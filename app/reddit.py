from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse


SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_]{1,20}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
POST_ID_RE = re.compile(r"^[A-Za-z0-9]+$")
COMMENT_PATH_RE = re.compile(r"/comments/([A-Za-z0-9]+)/?")

SUBREDDIT_SORTS = {"hot", "new", "top", "rising", "controversial"}
SEARCH_SORTS = {"relevance", "hot", "top", "new", "comments"}


def clamp_limit(value: int | str | None, default: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, 1), maximum)


def clean_subreddit(value: str) -> str:
    candidate = value.strip()
    parsed = urlparse(candidate)
    if parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0].lower() == "r":
            candidate = parts[1]
    elif candidate.lower().startswith("r/"):
        candidate = candidate.split("/", 1)[1]

    candidate = candidate.strip("/").split("/")[0]
    if not SUBREDDIT_RE.fullmatch(candidate):
        raise ValueError("Enter a subreddit name such as python or r/python.")
    return candidate


def clean_username(value: str) -> str:
    candidate = value.strip()
    parsed = urlparse(candidate)
    if parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0].lower() in {"u", "user"}:
            candidate = parts[1]
    elif candidate.lower().startswith(("u/", "user/")):
        candidate = candidate.split("/", 1)[1]

    candidate = candidate.strip("/").split("/")[0]
    if not USERNAME_RE.fullmatch(candidate):
        raise ValueError("Enter a Reddit username such as spez or u/spez.")
    return candidate


def extract_post_id(value: str) -> str:
    candidate = value.strip()
    parsed = urlparse(candidate)
    if parsed.netloc:
        match = COMMENT_PATH_RE.search(parsed.path)
        if match:
            return match.group(1)
    else:
        match = COMMENT_PATH_RE.search(candidate)
        if match:
            return match.group(1)
        if POST_ID_RE.fullmatch(candidate):
            return candidate

    raise ValueError("Enter a Reddit post URL or post id.")


def subreddit_about_url(subreddit: str) -> str:
    return f"https://www.reddit.com/r/{quote(clean_subreddit(subreddit))}/about.json?raw_json=1"


def subreddit_listing_url(subreddit: str, sort: str, limit: int) -> str:
    clean_sort = sort if sort in SUBREDDIT_SORTS else "hot"
    query = urlencode({"limit": limit, "raw_json": 1})
    return f"https://www.reddit.com/r/{quote(clean_subreddit(subreddit))}/{clean_sort}.json?{query}"


def old_subreddit_listing_url(subreddit: str, sort: str) -> str:
    clean_sort = sort if sort in SUBREDDIT_SORTS else "hot"
    path_sort = "" if clean_sort == "hot" else f"{clean_sort}/"
    return f"https://old.reddit.com/r/{quote(clean_subreddit(subreddit))}/{path_sort}"


def post_thread_url(post: str, comment_limit: int) -> str:
    post_id = extract_post_id(post)
    query = urlencode({"limit": comment_limit, "raw_json": 1, "sort": "top"})
    return f"https://www.reddit.com/comments/{quote(post_id)}.json?{query}"


def user_about_url(username: str) -> str:
    return f"https://www.reddit.com/user/{quote(clean_username(username))}/about.json?raw_json=1"


def user_submitted_url(username: str, limit: int) -> str:
    query = urlencode({"limit": limit, "raw_json": 1})
    return f"https://www.reddit.com/user/{quote(clean_username(username))}/submitted.json?{query}"


def search_url(query_text: str, sort: str, limit: int, subreddit: str | None = None) -> str:
    clean_sort = sort if sort in SEARCH_SORTS else "relevance"
    params = {"q": query_text.strip(), "limit": limit, "sort": clean_sort, "raw_json": 1}
    if not params["q"]:
        raise ValueError("Enter a Reddit search query.")
    if subreddit:
        params["restrict_sr"] = 1
        path = f"https://www.reddit.com/r/{quote(clean_subreddit(subreddit))}/search.json"
    else:
        path = "https://www.reddit.com/search.json"
    return f"{path}?{urlencode(params)}"


def absolute_reddit_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/"):
        return f"https://www.reddit.com{value}"
    return value


def parse_created_utc(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def listing_children(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        children: list[dict[str, Any]] = []
        for item in payload:
            children.extend(listing_children(item))
        return children

    if not isinstance(payload, dict):
        return []

    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("children"), list):
        return [child for child in data["children"] if isinstance(child, dict)]
    return []


def parse_listing_posts(payload: Any) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    for child in listing_children(payload):
        if child.get("kind") != "t3":
            continue
        data = child.get("data")
        if isinstance(data, dict):
            post = post_from_data(data)
            if post:
                posts.append(post)
    return posts


def parse_old_reddit_listing(html_text: str, limit: int) -> list[dict[str, Any]]:
    parser = _OldRedditListingParser()
    parser.feed(html_text)
    return parser.posts[:limit]


def parse_post_thread(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(payload, list) and payload:
        posts = parse_listing_posts(payload[0])
        post_id = posts[0]["id"] if posts else None
        comments = parse_comment_listing(payload[1], post_id) if len(payload) > 1 else []
        return posts, comments

    posts = parse_listing_posts(payload)
    return posts, []


def parse_comment_listing(payload: Any, post_id: str | None) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for child in listing_children(payload):
        comments.extend(_walk_comment_child(child, post_id))
    return comments


def post_from_data(data: dict[str, Any]) -> dict[str, Any] | None:
    post_id = data.get("id")
    if not post_id:
        return None

    return {
        "id": str(post_id),
        "fullname": data.get("name"),
        "subreddit": data.get("subreddit"),
        "title": data.get("title"),
        "author": data.get("author"),
        "selftext": data.get("selftext") or "",
        "url": data.get("url_overridden_by_dest") or data.get("url"),
        "permalink": absolute_reddit_url(data.get("permalink")),
        "thumbnail": _clean_image_url(data.get("thumbnail")),
        "media_url": _extract_media_url(data),
        "created_at": parse_created_utc(data.get("created_utc")),
        "score": _int_or_none(data.get("score")),
        "upvote_ratio": _float_or_none(data.get("upvote_ratio")),
        "num_comments": _int_or_none(data.get("num_comments")),
        "is_self": data.get("is_self"),
        "over18": data.get("over_18"),
        "flair_text": data.get("link_flair_text"),
        "raw": data,
    }


def parse_subreddit_about(payload: Any) -> dict[str, Any] | None:
    data = _thing_data(payload)
    display = data.get("display_name") or data.get("display_name_prefixed")
    if not display:
        return None

    name = str(display).removeprefix("r/")
    return {
        "name": name,
        "display_name": data.get("display_name_prefixed") or f"r/{name}",
        "title": data.get("title"),
        "public_description": data.get("public_description") or data.get("description"),
        "subscribers": _int_or_none(data.get("subscribers")),
        "created_at": parse_created_utc(data.get("created_utc")),
        "over18": data.get("over18"),
        "icon_url": _clean_image_url(data.get("icon_img") or data.get("community_icon")),
        "banner_url": _clean_image_url(data.get("banner_background_image") or data.get("banner_img")),
        "raw": data,
    }


def parse_user_about(payload: Any) -> dict[str, Any] | None:
    data = _thing_data(payload)
    username = data.get("name") or data.get("subreddit", {}).get("display_name")
    if not username:
        return None

    total_karma = sum(
        value or 0
        for value in (
            _int_or_none(data.get("link_karma")),
            _int_or_none(data.get("comment_karma")),
            _int_or_none(data.get("awardee_karma")),
            _int_or_none(data.get("awarder_karma")),
        )
    )
    profile = data.get("subreddit") if isinstance(data.get("subreddit"), dict) else {}

    return {
        "username": username,
        "display_name": data.get("subreddit", {}).get("display_name_prefixed") if isinstance(data.get("subreddit"), dict) else username,
        "public_description": profile.get("public_description"),
        "icon_url": _clean_image_url(profile.get("icon_img") or data.get("icon_img")),
        "created_at": parse_created_utc(data.get("created_utc")),
        "total_karma": total_karma,
        "raw": data,
    }


def _walk_comment_child(child: dict[str, Any], post_id: str | None) -> list[dict[str, Any]]:
    if child.get("kind") != "t1":
        return []

    data = child.get("data")
    if not isinstance(data, dict) or not data.get("id"):
        return []

    comment = {
        "id": str(data.get("id")),
        "fullname": data.get("name"),
        "post_id": post_id,
        "parent_id": data.get("parent_id"),
        "author": data.get("author"),
        "body": data.get("body") or "",
        "score": _int_or_none(data.get("score")),
        "created_at": parse_created_utc(data.get("created_utc")),
        "permalink": absolute_reddit_url(data.get("permalink")),
        "raw": data,
    }

    comments = [comment]
    replies = data.get("replies")
    if isinstance(replies, dict):
        comments.extend(parse_comment_listing(replies, post_id))
    return comments


def _thing_data(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return data
    return {}


def _extract_media_url(data: dict[str, Any]) -> str | None:
    media = data.get("media")
    if isinstance(media, dict):
        reddit_video = media.get("reddit_video")
        if isinstance(reddit_video, dict) and reddit_video.get("fallback_url"):
            return reddit_video["fallback_url"]

    preview = data.get("preview")
    if isinstance(preview, dict):
        images = preview.get("images")
        if isinstance(images, list) and images:
            source = images[0].get("source") if isinstance(images[0], dict) else None
            if isinstance(source, dict):
                return _clean_image_url(source.get("url"))

    hint = data.get("post_hint")
    if hint in {"image", "hosted:video", "rich:video"}:
        return _clean_image_url(data.get("url_overridden_by_dest") or data.get("url"))
    return None


def _clean_image_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if value in {"self", "default", "nsfw", "spoiler"}:
        return None
    return html.unescape(value)


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


class _OldRedditListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.posts: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._depth = 0
        self._capture_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}

        if self._current is None and tag == "div" and _is_old_reddit_post(attr):
            self._current = _old_reddit_post_from_attrs(attr)
            self._depth = 1
            self._title_parts = []
            return

        if self._current is None:
            return

        if tag == "div":
            self._depth += 1
        elif tag == "a" and "title" in attr.get("class", "").split():
            self._capture_title = True
            if attr.get("href") and not self._current.get("url"):
                self._current["url"] = absolute_reddit_url(attr["href"])
        elif tag == "span" and "linkflairlabel" in attr.get("class", "").split():
            self._current["flair_text"] = attr.get("title") or None

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return

        if tag == "a" and self._capture_title:
            self._capture_title = False
            title = " ".join(part.strip() for part in self._title_parts if part.strip())
            if title:
                self._current["title"] = title

        if tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                if self._current.get("id") and self._current.get("title"):
                    self.posts.append(self._current)
                self._current = None
                self._title_parts = []
                self._capture_title = False


def _is_old_reddit_post(attrs: dict[str, str]) -> bool:
    fullname = attrs.get("data-fullname", "")
    class_names = attrs.get("class", "")
    return fullname.startswith("t3_") and attrs.get("data-type") == "link" and "thing" in class_names


def _old_reddit_post_from_attrs(attrs: dict[str, str]) -> dict[str, Any]:
    fullname = attrs.get("data-fullname") or ""
    permalink = absolute_reddit_url(attrs.get("data-permalink"))
    url = absolute_reddit_url(attrs.get("data-url")) or permalink
    timestamp = _int_or_none(attrs.get("data-timestamp"))

    return {
        "id": fullname.removeprefix("t3_"),
        "fullname": fullname,
        "subreddit": attrs.get("data-subreddit") or None,
        "title": None,
        "author": attrs.get("data-author") or None,
        "selftext": "",
        "url": url,
        "permalink": permalink,
        "thumbnail": None,
        "media_url": None,
        "created_at": parse_created_utc(timestamp / 1000 if timestamp else None),
        "score": _int_or_none(attrs.get("data-score")),
        "upvote_ratio": None,
        "num_comments": _int_or_none(attrs.get("data-comments-count")),
        "is_self": (attrs.get("data-domain") or "").startswith("self."),
        "over18": _bool_string(attrs.get("data-nsfw")),
        "flair_text": None,
        "raw": {"source": "old_reddit_html", "attrs": attrs},
    }


def _bool_string(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None
