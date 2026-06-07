from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import database, reddit, repository
from .config import get_settings


BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()

app = FastAPI(title=settings.web_app_title)
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
    post_limit: int = Form(settings.reddit_default_limit),
    comment_limit: int = Form(100),
    subreddit_filter: str = Form(""),
    include_comments: str | None = Form(None),
    use_js: str | None = Form(None),
) -> HTMLResponse | RedirectResponse:
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

    try:
        normalized = _normalize_job_input(target_type, target, sort, post_limit, comment_limit, subreddit_filter, use_js)
    except ValueError as exc:
        return _render_index(request, error=str(exc), form=form, status_code=400)

    with database.connection(settings) as conn:
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


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: str) -> HTMLResponse:
    with database.connection(settings) as conn:
        job = repository.get_job(conn, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        posts = repository.list_job_posts(conn, job_id)

    return templates.TemplateResponse(
        "job.html",
        {
            "request": request,
            "title": settings.web_app_title,
            "job": job,
            "posts": posts,
            "autorefresh": job["status"] in {"queued", "running"},
            "format_dt": format_dt,
        },
    )


@app.get("/posts/{post_id}", response_class=HTMLResponse)
def post_detail(request: Request, post_id: str) -> HTMLResponse:
    with database.connection(settings) as conn:
        post = repository.get_post(conn, post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        comments = repository.list_post_comments(conn, post_id)

    return templates.TemplateResponse(
        "post.html",
        {
            "request": request,
            "title": settings.web_app_title,
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
        stats = repository.dashboard_stats(conn)
        jobs = repository.list_recent_jobs(conn)
        posts = repository.list_recent_posts(conn)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": settings.web_app_title,
            "stats": stats,
            "jobs": jobs,
            "posts": posts,
            "error": error,
            "form": form or {},
            "settings": settings,
            "format_dt": format_dt,
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
) -> dict[str, Any]:
    clean_type = target_type.strip().lower()
    clean_target = target.strip()
    clean_sort = sort.strip().lower()
    limit = reddit.clamp_limit(post_limit, settings.reddit_default_limit, settings.reddit_max_limit)
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


def format_dt(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    return str(value)
