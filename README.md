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
# Set POSTGRES_PASSWORD in .env before starting the containers.
docker compose up --build
```

Open `http://localhost:8000`, then submit Crawlbase credentials and crawler tuning from `Settings`.

The collector will leave jobs queued until at least one Crawlbase token is saved from the UI. Settings are stored in PostgreSQL and are read by both the web and collector containers.

## Configuration

- `.env`: PostgreSQL bootstrap values for the shared database container. `POSTGRES_PASSWORD` is required before the UI can start.
- UI settings: Crawlbase normal token, JavaScript token, proxy country, device, request timeout, collector poll delay, request delay, and post limits.

Crawlbase secrets are not echoed back into forms. The settings page only indicates whether each token is present.

## Notes

Use this for public Reddit data and respect Reddit's terms, privacy expectations, and reasonable rate limits. Crawlbase's Reddit guidance emphasizes anti-blocking infrastructure, controlled scraping, proxies, and rate limiting; this project keeps those concerns in the collector and makes the delay explicit.

Async Crawlbase requests are not used here because the Crawling API documentation currently limits `async=true` support to LinkedIn URLs.

## Verify

```sh
python -m unittest discover -s tests
python -m compileall app tests
docker compose config
```
