# Reddit Scraper Collector

A multi-container Reddit crawler with pluggable scraper providers and PostgreSQL as the shared state store between the web UI and collector.

## Architecture

- `web`: FastAPI UI for creating crawl jobs and viewing stored posts/comments.
- `collector`: polling worker that claims queued jobs, calls the selected provider, normalizes Reddit data, and writes results.
- `shared-db`: PostgreSQL container shared by the other services on the Compose network.

Provider-specific scraping lives behind `app.providers.ScraperProvider`, so the collector can claim and persist jobs without knowing whether Crawlbase or Apify produced the result.

## Providers

- Crawlbase: uses the Crawling API endpoint with `token`, URL-encoded `url`, `format=json`, gzip, a 95 second default timeout, optional `country`/`device`, and optional JavaScript rendering retry when a normal-token response is empty or returns `pc_status=525`. Crawlbase supports subreddit, post, user, and search jobs.
- Apify: uses the official `apify-client` package to run a standard Apify scraper actor and read the run's default dataset. The default actor is `apify/web-scraper`, configured with a browser page function for old Reddit. `apify/cheerio-scraper` is also supported by changing the actor in Settings, but Reddit often blocks raw HTTP scraping paths.

The Apify provider currently supports subreddit and post jobs. It uses single-page guardrails (`linkSelector=""`, `maxPagesPerCrawl=1`, `maxResultsPerCrawl=1`, `maxConcurrency=1`) so a job does not accidentally fan out across Reddit. The default Apify proxy group is `RESIDENTIAL`, which is usually more appropriate for social media targets than automatic datacenter proxy selection.

## Crawl Types

- Subreddit: posts from `hot`, `new`, `top`, `rising`, or `controversial`, plus subreddit metadata.
- Post: post details and comment tree from a Reddit post URL or id.
- User: public user profile metadata and submitted posts.
- Search: global or subreddit-scoped Reddit search results.

Each Crawlbase job can optionally collect comments for the posts it finds. Keep that setting modest because it adds one provider request per post. Apify post jobs collect comments from the submitted post page.

## Run

```sh
cp .env.example .env
# Set POSTGRES_PASSWORD in .env before starting the containers.
docker compose up --build
```

Open `http://localhost:8000`, then submit provider credentials and crawler tuning from `Settings`.

The collector will leave jobs queued until at least one provider token is saved from the UI. Settings are stored in PostgreSQL and are read by both the web and collector containers.

## Configuration

- `.env`: PostgreSQL bootstrap values for the shared database container. `POSTGRES_PASSWORD` is required before the UI can start.
- UI settings: default provider, Crawlbase normal token, Crawlbase JavaScript token, Apify API token, Apify actor id, proxy country, timeouts, retries, collector poll delay, request delay, and post limits.

Provider secrets are not echoed back into forms. The settings page only indicates whether each token is present.

## Notes

Use this for public Reddit data and respect Reddit's terms, privacy expectations, and reasonable rate limits. Crawlbase's Reddit guidance emphasizes anti-blocking infrastructure, controlled scraping, proxies, and rate limiting; this project keeps those concerns in the collector and makes the delay explicit.

Async Crawlbase requests are not used here because the Crawling API documentation currently limits `async=true` support to LinkedIn URLs.

Apify's full-permission actors may require a one-time approval in Apify Console before API, CLI, MCP, or scheduled runs can start. If a job fails with an approval URL, approve that actor in Console and rerun the job. Apify documents that this approval cannot be granted through the API.

## Verify

```sh
python -m unittest discover -s tests
python -m compileall app tests
docker compose config
```
