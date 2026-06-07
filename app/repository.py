from __future__ import annotations

import uuid
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from . import database
from .config import Settings, get_settings


def create_job(
    conn: Connection,
    *,
    target_type: str,
    target: str,
    provider: str,
    sort: str,
    post_limit: int,
    include_comments: bool,
    options: dict[str, Any] | None = None,
) -> str:
    job_id = str(uuid.uuid4())
    row = conn.execute(
        """
        INSERT INTO crawl_jobs (
            id, target_type, target, provider, sort, post_limit, include_comments, options
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (job_id, target_type, target, provider, sort, post_limit, include_comments, Jsonb(options or {})),
    ).fetchone()
    return str(row["id"])


def claim_next_job(settings: Settings | None = None) -> dict[str, Any] | None:
    resolved = settings or get_settings()
    with database.connection(resolved, autocommit=False) as conn:
        with conn.transaction():
            row = conn.execute(
                """
                SELECT *
                FROM crawl_jobs
                WHERE status = 'queued'
                ORDER BY requested_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            ).fetchone()
            if row is None:
                return None

            updated = conn.execute(
                """
                UPDATE crawl_jobs
                SET status = 'running',
                    started_at = now(),
                    updated_at = now(),
                    error = NULL
                WHERE id = %s
                RETURNING *
                """,
                (row["id"],),
            ).fetchone()
            return dict(updated)


def complete_job(
    conn: Connection,
    job_id: str,
    *,
    stats: dict[str, Any],
    last_response: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        UPDATE crawl_jobs
        SET status = 'completed',
            completed_at = now(),
            updated_at = now(),
            stats = %s,
            last_response = %s,
            error = NULL
        WHERE id = %s
        """,
        (Jsonb(stats), Jsonb(last_response or {}), job_id),
    )


def fail_job(
    conn: Connection,
    job_id: str,
    *,
    error: str,
    stats: dict[str, Any] | None = None,
    last_response: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        UPDATE crawl_jobs
        SET status = 'failed',
            completed_at = now(),
            updated_at = now(),
            error = %s,
            stats = %s,
            last_response = %s
        WHERE id = %s
        """,
        (error, Jsonb(stats or {}), Jsonb(last_response or {}), job_id),
    )


def save_subreddit(conn: Connection, subreddit: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO subreddits (
            name, display_name, title, public_description, subscribers,
            created_at, over18, icon_url, banner_url, raw, last_seen_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (name) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            title = EXCLUDED.title,
            public_description = EXCLUDED.public_description,
            subscribers = EXCLUDED.subscribers,
            created_at = EXCLUDED.created_at,
            over18 = EXCLUDED.over18,
            icon_url = EXCLUDED.icon_url,
            banner_url = EXCLUDED.banner_url,
            raw = EXCLUDED.raw,
            last_seen_at = now()
        """,
        (
            subreddit.get("name"),
            subreddit.get("display_name"),
            subreddit.get("title"),
            subreddit.get("public_description"),
            subreddit.get("subscribers"),
            subreddit.get("created_at"),
            subreddit.get("over18"),
            subreddit.get("icon_url"),
            subreddit.get("banner_url"),
            Jsonb(subreddit.get("raw") or {}),
        ),
    )


def save_user(conn: Connection, user: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO users (
            username, display_name, public_description, icon_url,
            created_at, total_karma, raw, last_seen_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (username) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            public_description = EXCLUDED.public_description,
            icon_url = EXCLUDED.icon_url,
            created_at = EXCLUDED.created_at,
            total_karma = EXCLUDED.total_karma,
            raw = EXCLUDED.raw,
            last_seen_at = now()
        """,
        (
            user.get("username"),
            user.get("display_name"),
            user.get("public_description"),
            user.get("icon_url"),
            user.get("created_at"),
            user.get("total_karma"),
            Jsonb(user.get("raw") or {}),
        ),
    )


def save_post(conn: Connection, post: dict[str, Any], job_id: str) -> None:
    subreddit = post.get("subreddit")
    if subreddit:
        conn.execute(
            """
            INSERT INTO subreddits (name, display_name)
            VALUES (%s, %s)
            ON CONFLICT (name) DO NOTHING
            """,
            (subreddit, f"r/{subreddit}"),
        )

    conn.execute(
        """
        INSERT INTO posts (
            id, fullname, job_id, subreddit, title, author, selftext, url,
            permalink, thumbnail, media_url, created_at, score, upvote_ratio,
            num_comments, is_self, over18, flair_text, raw, last_seen_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, now()
        )
        ON CONFLICT (id) DO UPDATE SET
            fullname = EXCLUDED.fullname,
            job_id = EXCLUDED.job_id,
            subreddit = EXCLUDED.subreddit,
            title = EXCLUDED.title,
            author = EXCLUDED.author,
            selftext = EXCLUDED.selftext,
            url = EXCLUDED.url,
            permalink = EXCLUDED.permalink,
            thumbnail = EXCLUDED.thumbnail,
            media_url = EXCLUDED.media_url,
            created_at = EXCLUDED.created_at,
            score = EXCLUDED.score,
            upvote_ratio = EXCLUDED.upvote_ratio,
            num_comments = EXCLUDED.num_comments,
            is_self = EXCLUDED.is_self,
            over18 = EXCLUDED.over18,
            flair_text = EXCLUDED.flair_text,
            raw = EXCLUDED.raw,
            last_seen_at = now()
        """,
        (
            post.get("id"),
            post.get("fullname"),
            job_id,
            subreddit,
            post.get("title"),
            post.get("author"),
            post.get("selftext"),
            post.get("url"),
            post.get("permalink"),
            post.get("thumbnail"),
            post.get("media_url"),
            post.get("created_at"),
            post.get("score"),
            post.get("upvote_ratio"),
            post.get("num_comments"),
            post.get("is_self"),
            post.get("over18"),
            post.get("flair_text"),
            Jsonb(post.get("raw") or {}),
        ),
    )


def save_comment(conn: Connection, comment: dict[str, Any], job_id: str) -> None:
    conn.execute(
        """
        INSERT INTO comments (
            id, fullname, job_id, post_id, parent_id, author, body,
            score, created_at, permalink, raw, last_seen_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (id) DO UPDATE SET
            fullname = EXCLUDED.fullname,
            job_id = EXCLUDED.job_id,
            post_id = EXCLUDED.post_id,
            parent_id = EXCLUDED.parent_id,
            author = EXCLUDED.author,
            body = EXCLUDED.body,
            score = EXCLUDED.score,
            created_at = EXCLUDED.created_at,
            permalink = EXCLUDED.permalink,
            raw = EXCLUDED.raw,
            last_seen_at = now()
        """,
        (
            comment.get("id"),
            comment.get("fullname"),
            job_id,
            comment.get("post_id"),
            comment.get("parent_id"),
            comment.get("author"),
            comment.get("body"),
            comment.get("score"),
            comment.get("created_at"),
            comment.get("permalink"),
            Jsonb(comment.get("raw") or {}),
        ),
    )


def dashboard_stats(conn: Connection) -> dict[str, Any]:
    return conn.execute(
        """
        SELECT
            (SELECT count(*) FROM crawl_jobs) AS jobs,
            (SELECT count(*) FROM crawl_jobs WHERE status = 'queued') AS queued,
            (SELECT count(*) FROM crawl_jobs WHERE status = 'running') AS running,
            (SELECT count(*) FROM posts) AS posts,
            (SELECT count(*) FROM comments) AS comments,
            (SELECT count(*) FROM subreddits) AS subreddits,
            (SELECT count(*) FROM users) AS users
        """
    ).fetchone()


def list_recent_jobs(conn: Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM crawl_jobs
        ORDER BY requested_at DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_job(conn: Connection, job_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM crawl_jobs WHERE id = %s", (job_id,)).fetchone()
    return dict(row) if row else None


def list_recent_posts(conn: Connection, limit: int = 25) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.*, COALESCE(c.comment_count, 0) AS comment_count
        FROM posts p
        LEFT JOIN (
            SELECT post_id, count(*) AS comment_count
            FROM comments
            GROUP BY post_id
        ) c ON c.post_id = p.id
        ORDER BY p.created_at DESC NULLS LAST, p.last_seen_at DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_job_posts(conn: Connection, job_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.*, COALESCE(c.comment_count, 0) AS comment_count
        FROM posts p
        LEFT JOIN (
            SELECT post_id, count(*) AS comment_count
            FROM comments
            GROUP BY post_id
        ) c ON c.post_id = p.id
        WHERE p.job_id = %s
        ORDER BY p.created_at DESC NULLS LAST, p.last_seen_at DESC
        """,
        (job_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_post(conn: Connection, post_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT p.*, COALESCE(c.comment_count, 0) AS comment_count
        FROM posts p
        LEFT JOIN (
            SELECT post_id, count(*) AS comment_count
            FROM comments
            GROUP BY post_id
        ) c ON c.post_id = p.id
        WHERE p.id = %s
        """,
        (post_id,),
    ).fetchone()
    return dict(row) if row else None


def list_post_comments(conn: Connection, post_id: str, limit: int = 500) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM comments
        WHERE post_id = %s
        ORDER BY score DESC NULLS LAST, created_at ASC NULLS LAST
        LIMIT %s
        """,
        (post_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]
