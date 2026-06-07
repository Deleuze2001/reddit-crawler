from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import database, reddit, repository, settings_store
from .config import get_settings
from .settings_store import CrawlerSettings


BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()

app = FastAPI(title="Reddit Crawlbase Collector")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def startup() -> None:
    database.run_migrations(settings)


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    with database.connection(settings) as conn:
        conn.execute("SELECT 1")
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return _render_index(request)


@app.post("/jobs", response_class=HTMLResponse)
def create_job(
    request: Request,
    target_type: str = Form(...),
    target: str = Form(...),
    sort: str = Form("hot"),
    post_limit: int = Form(25),
    comment_limit: int = Form(100),
    subreddit_filter: str = Form(""),
    include_comments: str | None = Form(None),
    use_js: str | None = Form(None),
) -> Any:
    form = {
        "target_type": target_type,
        "target": target,
        "sort": sort,
        "post_limit": post_limit,
        "comment_limit": comment_limit,
        "subreddit_filter": subreddit_filter,
        "include_comments": include_comments,
        "use_js": use_js,
    }

    with database.connection(settings) as conn:
        crawler_settings = settings_store.get_crawler_settings(conn)
        try:
            normalized = _normalize_job_input(
                target_type,
                target,
                sort,
                post_limit,
                comment_limit,
                subreddit_filter,
                use_js,
                crawler_settings,
            )
        except ValueError as exc:
            return _render_index(request, error=str(exc), form=form, status_code=400)

        job_id = repository.create_job(
            conn,
            target_type=normalized["target_type"],
            target=normalized["target"],
            sort=normalized["sort"],
            post_limit=normalized["post_limit"],
            include_comments=include_comments == "on",
            options=normalized["options"],
        )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    return _render_settings(request, saved=request.query_params.get("saved") == "1")


@app.post("/settings", response_class=HTMLResponse)
def update_settings(
    request: Request,
    app_title: str = Form("Reddit Crawlbase Collector"),
    crawlbase_normal_token: str = Form(""),
    crawlbase_js_token: str = Form(""),
    clear_normal_token: str | None = Form(None),
    clear_js_token: str | None = Form(None),
    crawlbase_country: str = Form("US"),
    crawlbase_device: str = Form("desktop"),
    crawlbase_timeout_seconds: float = Form(95.0),
    crawlbase_rate_limit_seconds: float = Form(2.0),
    collector_poll_seconds: float = Form(5.0),
    reddit_default_limit: int = Form(25),
    reddit_max_limit: int = Form(100),
) -> Any:
    try:
        updates = _normalize_settings_input(
            app_title=app_title,
            crawlbase_normal_token=crawlbase_normal_token,
            crawlbase_js_token=crawlbase_js_token,
            clear_normal_token=clear_normal_token == "on",
            clear_js_token=clear_js_token == "on",
            crawlbase_country=crawlbase_country,
            crawlbase_device=crawlbase_device,
            crawlbase_timeout_seconds=crawlbase_timeout_seconds,
            crawlbase_rate_limit_seconds=crawlbase_rate_limit_seconds,
            collector_poll_seconds=collector_poll_seconds,
            reddit_default_limit=reddit_default_limit,
            reddit_max_limit=reddit_max_limit,
        )
    except ValueError as exc:
        return _render_settings(request, error=str(exc), status_code=400)

    with database.connection(settings) as conn:
        settings_store.update_crawler_settings(conn, updates)
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: str) -> HTMLResponse:
    with database.connection(settings) as conn:
        crawler_settings = settings_store.get_crawler_settings(conn)
        job = repository.get_job(conn, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        posts = repository.list_job_posts(conn, job_id)

    return templates.TemplateResponse(
        request,
        "job.html",
        {
            "request": request,
            "title": crawler_settings.app_title,
            "job": job,
            "posts": posts,
            "autorefresh": job["status"] in {"queued", "running"},
            "format_dt": format_dt,
        },
    )


@app.get("/posts/{post_id}", response_class=HTMLResponse)
def post_detail(request: Request, post_id: str) -> HTMLResponse:
    with database.connection(settings) as conn:
        crawler_settings = settings_store.get_crawler_settings(conn)
        post = repository.get_post(conn, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        comments = repository.list_post_comments(conn, post_id)

    return templates.TemplateResponse(
        request,
        "post.html",
        {
            "request": request,
            "title": crawler_settings.app_title,
            "post": post,
            "comments": comments,
            "format_dt": format_dt,
        },
    )


def _render_index(
    request: Request,
    *,
    error: str | None = None,
    form: dict[str, Any] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    with database.connection(settings) as conn:
        crawler_settings = settings_store.get_crawler_settings(conn)
        stats = repository.dashboard_stats(conn)
        jobs = repository.list_recent_jobs(conn)
        posts = repository.list_recent_posts(conn)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "title": crawler_settings.app_title,
            "stats": stats,
            "jobs": jobs,
            "posts": posts,
            "error": error,
            "form": form or {},
            "settings": crawler_settings,
            "format_dt": format_dt,
        },
        status_code=status_code,
    )


def _render_settings(
    request: Request,
    *,
    error: str | None = None,
    saved: bool = False,
    status_code: int = 200,
) -> HTMLResponse:
    with database.connection(settings) as conn:
        crawler_settings = settings_store.get_crawler_settings(conn)

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "title": crawler_settings.app_title,
            "runtime": crawler_settings,
            "public_settings": settings_store.public_settings(crawler_settings),
            "device_choices": sorted(settings_store.DEVICE_CHOICES),
            "error": error,
            "saved": saved,
        },
        status_code=status_code,
    )


def _normalize_job_input(
    target_type: str,
    target: str,
    sort: str,
    post_limit: int,
    comment_limit: int,
    subreddit_filter: str,
    use_js: str | None,
    crawler_settings: CrawlerSettings,
) -> dict[str, Any]:
    clean_type = target_type.strip().lower()
    clean_target = target.strip()
    clean_sort = sort.strip().lower()
    limit = reddit.clamp_limit(post_limit, crawler_settings.reddit_default_limit, crawler_settings.reddit_max_limit)
    options: dict[str, Any] = {
        "comment_limit": reddit.clamp_limit(comment_limit, 100, 500),
    }
    if use_js == "on":
        options["use_js"] = True

    if clean_type == "subreddit":
        clean_target = reddit.clean_subreddit(clean_target)
        if clean_sort not in reddit.SUBREDDIT_SORTS:
            clean_sort = "hot"
    elif clean_type == "post":
        reddit.extract_post_id(clean_target)
        clean_sort = "top"
    elif clean_type == "user":
        clean_target = reddit.clean_username(clean_target)
        clean_sort = "new"
    elif clean_type == "search":
        if not clean_target:
            raise ValueError("Enter a Reddit search query.")
        if clean_sort not in reddit.SEARCH_SORTS:
            clean_sort = "relevance"
        if subreddit_filter.strip():
            options["subreddit"] = reddit.clean_subreddit(subreddit_filter)
    else:
        raise ValueError("Choose subreddit, post, user, or search.")

    return {
        "target_type": clean_type,
        "target": clean_target,
        "sort": clean_sort,
        "post_limit": limit,
        "options": options,
    }


def _normalize_settings_input(
    *,
    app_title: str,
    crawlbase_normal_token: str,
    crawlbase_js_token: str,
    clear_normal_token: bool,
    clear_js_token: bool,
    crawlbase_country: str,
    crawlbase_device: str,
    crawlbase_timeout_seconds: float,
    crawlbase_rate_limit_seconds: float,
    collector_poll_seconds: float,
    reddit_default_limit: int,
    reddit_max_limit: int,
) -> dict[str, Any]:
    title = app_title.strip() or settings_store.DEFAULT_VALUES["app_title"]
    country = crawlbase_country.strip().upper()
    if country and (len(country) != 2 or not country.isalpha()):
        raise ValueError("Country must be a two-letter code, or blank.")

    device = crawlbase_device.strip().lower()
    if device not in settings_store.DEVICE_CHOICES:
        raise ValueError("Choose desktop, tablet, or mobile.")

    if crawlbase_timeout_seconds < 30 or crawlbase_timeout_seconds > 300:
        raise ValueError("Timeout must be between 30 and 300 seconds.")
    if crawlbase_rate_limit_seconds < 0 or crawlbase_rate_limit_seconds > 60:
        raise ValueError("Rate limit delay must be between 0 and 60 seconds.")
    if collector_poll_seconds < 1 or collector_poll_seconds > 300:
        raise ValueError("Collector poll delay must be between 1 and 300 seconds.")
    if reddit_max_limit < 1 or reddit_max_limit > 500:
        raise ValueError("Maximum post limit must be between 1 and 500.")
    if reddit_default_limit < 1 or reddit_default_limit > reddit_max_limit:
        raise ValueError("Default post limit must be between 1 and the maximum post limit.")

    updates: dict[str, Any] = {
        "app_title": title,
        "crawlbase_country": country,
        "crawlbase_device": device,
        "crawlbase_timeout_seconds": crawlbase_timeout_seconds,
        "crawlbase_rate_limit_seconds": crawlbase_rate_limit_seconds,
        "collector_poll_seconds": collector_poll_seconds,
        "reddit_default_limit": reddit_default_limit,
        "reddit_max_limit": reddit_max_limit,
    }

    normal_token = crawlbase_normal_token.strip()
    js_token = crawlbase_js_token.strip()
    if clear_normal_token:
        updates["crawlbase_normal_token"] = ""
    elif normal_token:
        updates["crawlbase_normal_token"] = normal_token

    if clear_js_token:
        updates["crawlbase_js_token"] = ""
    elif js_token:
        updates["crawlbase_js_token"] = js_token

    return updates


def format_dt(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    return str(value)
