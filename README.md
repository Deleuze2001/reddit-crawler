# Reddit Crawlbase Collector

A multi-container Reddit crawler using Crawlbase for collection and PostgreSQL as the shared state store between the web UI and collector.

## Architecture

- `web`: FastAPI UI for creating crawl jobs and viewing stored posts/comments.
- `collector`: polling worker that claims queued jobs, calls Crawlbase, parses Reddit JSON, and writes results.
- `shared-db`: PostgreSQL container shared by the other services on the Compose network.

The collector uses Crawlbase's Crawling API endpoint with `token`, URL-encoded `url`, `format=json`, gzip, a 95 second default timeout, optional `country`/`device`, and optional JavaScript rendering retry when a normal-token response is empty or returns `pc_status=525`. Reddit jobs are normalized to public JSON endpoints such as subreddit listings, post threads, user submissions, and search results before being requested through Crawlbase.

## Crawl Types

- Subreddit: posts from `hot`, `new`, `top`, `rising`, or `controversial`, plus subreddit metadata.
- Post: post details and comment tree from a Reddit post URL or id.
- User: public user profile metadata and submitted posts.
- Search: global or subreddit-scoped Reddit search results.

Each job can optionally collect comments for the posts it finds. Keep that setting modest because it adds one Crawlbase request per post.

## Run

```sh
cp .env.example .env
# Fill in CRAWLBASE_NORMAL_TOKEN and optionally CRAWLBASE_JS_TOKEN.
docker compose up --build
```

Open `http://localhost:8000`.

The collector will leave jobs queued until at least one Crawlbase token is available. After editing `.env`, restart the collector:

```sh
docker compose up -d collector
```

## Configuration

- `CRAWLBASE_NORMAL_TOKEN`: normal Crawlbase token for JSON/static responses.
- `CRAWLBASE_JS_TOKEN`: JavaScript token for rendered fallback or explicit JS jobs.
- `CRAWLBASE_COUNTRY`: optional two-letter proxy country, default `US`.
- `CRAWLBASE_DEVICE`: `desktop`, `tablet`, or `mobile`, default `desktop`.
- `CRAWLBASE_TIMEOUT_SECONDS`: default `95`, matching Crawlbase's recommendation for slower rendered crawls.
- `CRAWLBASE_RATE_LIMIT_SECONDS`: delay between Crawlbase calls per collector, default `2.0`.
- `REDDIT_DEFAULT_LIMIT`: default number of posts, default `25`.
- `REDDIT_MAX_LIMIT`: maximum posts accepted by the UI, default `100`.

## Notes

Use this for public Reddit data and respect Reddit's terms, privacy expectations, and reasonable rate limits. Crawlbase's Reddit guidance emphasizes anti-blocking infrastructure, controlled scraping, proxies, and rate limiting; this project keeps those concerns in the collector and makes the delay explicit.

Async Crawlbase requests are not used here because the Crawling API documentation currently limits `async=true` support to LinkedIn URLs.

## Verify

```sh
python -m unittest discover -s tests
python -m compileall app tests
docker compose config
```
