CREATE TABLE IF NOT EXISTS crawl_jobs (
    id UUID PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (target_type IN ('subreddit', 'post', 'user', 'search')),
    target TEXT NOT NULL,
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
