CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    is_secret BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO app_settings (key, value, is_secret)
VALUES
    ('app_title', 'Reddit Scraper Collector', false),
    ('default_scraper_provider', 'crawlbase', false),
    ('crawlbase_normal_token', '', true),
    ('crawlbase_js_token', '', true),
    ('crawlbase_country', 'US', false),
    ('crawlbase_device', 'desktop', false),
    ('crawlbase_timeout_seconds', '95', false),
    ('crawlbase_rate_limit_seconds', '2.0', false),
    ('collector_poll_seconds', '5', false),
    ('reddit_default_limit', '25', false),
    ('reddit_max_limit', '100', false),
    ('apify_token', '', true),
    ('apify_actor_id', 'apify/cheerio-scraper', false),
    ('apify_run_timeout_seconds', '300', false),
    ('apify_page_load_timeout_seconds', '90', false),
    ('apify_page_function_timeout_seconds', '60', false),
    ('apify_max_request_retries', '2', false),
    ('apify_max_scroll_height_pixels', '8000', false),
    ('apify_proxy_country', 'US', false),
    ('apify_use_apify_proxy', 'true', false),
    ('apify_use_chrome', 'true', false)
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id UUID PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (target_type IN ('subreddit', 'post', 'user', 'search')),
    target TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'crawlbase' CHECK (provider IN ('crawlbase', 'apify')),
    sort TEXT NOT NULL DEFAULT 'hot',
    post_limit INTEGER NOT NULL DEFAULT 25 CHECK (post_limit BETWEEN 1 AND 500),
    include_comments BOOLEAN NOT NULL DEFAULT false,
    options JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error TEXT,
    stats JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_response JSONB NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE IF EXISTS crawl_jobs
    ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'crawlbase';

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status_requested_at
    ON crawl_jobs (status, requested_at);

CREATE TABLE IF NOT EXISTS subreddits (
    name TEXT PRIMARY KEY,
    display_name TEXT,
    title TEXT,
    public_description TEXT,
    subscribers INTEGER,
    created_at TIMESTAMPTZ,
    over18 BOOLEAN,
    icon_url TEXT,
    banner_url TEXT,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    display_name TEXT,
    public_description TEXT,
    icon_url TEXT,
    created_at TIMESTAMPTZ,
    total_karma INTEGER,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    fullname TEXT,
    job_id UUID REFERENCES crawl_jobs (id) ON DELETE SET NULL,
    subreddit TEXT REFERENCES subreddits (name) ON DELETE SET NULL,
    title TEXT,
    author TEXT,
    selftext TEXT,
    url TEXT,
    permalink TEXT,
    thumbnail TEXT,
    media_url TEXT,
    created_at TIMESTAMPTZ,
    score INTEGER,
    upvote_ratio NUMERIC,
    num_comments INTEGER,
    is_self BOOLEAN,
    over18 BOOLEAN,
    flair_text TEXT,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_posts_job_id ON posts (job_id);
CREATE INDEX IF NOT EXISTS idx_posts_subreddit_created_at ON posts (subreddit, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_last_seen_at ON posts (last_seen_at DESC);

CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    fullname TEXT,
    job_id UUID REFERENCES crawl_jobs (id) ON DELETE SET NULL,
    post_id TEXT REFERENCES posts (id) ON DELETE CASCADE,
    parent_id TEXT,
    author TEXT,
    body TEXT,
    score INTEGER,
    created_at TIMESTAMPTZ,
    permalink TEXT,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_comments_job_id ON comments (job_id);
CREATE INDEX IF NOT EXISTS idx_comments_post_id_created_at ON comments (post_id, created_at);
