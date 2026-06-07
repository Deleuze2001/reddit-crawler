from __future__ import annotations

import unittest

from app.providers.apify_provider import ApifyProvider
from app.settings_store import DEFAULT_VALUES, settings_from_values


class ApifyProviderTests(unittest.TestCase):
    def test_build_run_input_uses_standard_cheerio_guardrails(self) -> None:
        provider = ApifyProvider(
            settings_from_values(
                DEFAULT_VALUES
                | {
                    "apify_token": "token",
                    "apify_proxy_country": "GB",
                    "apify_use_chrome": "true",
                }
            )
        )

        run_input = provider.build_run_input("https://old.reddit.com/r/python/", "subreddit", 5, 20)

        self.assertEqual(run_input["startUrls"][0]["url"], "https://old.reddit.com/r/python/")
        self.assertEqual(run_input["linkSelector"], "")
        self.assertEqual(run_input["maxPagesPerCrawl"], 1)
        self.assertEqual(run_input["maxResultsPerCrawl"], 1)
        self.assertEqual(run_input["maxConcurrency"], 1)
        self.assertEqual(run_input["proxyConfiguration"]["countryCode"], "GB")
        self.assertEqual(run_input["customData"]["actorId"], "apify/cheerio-scraper")
        self.assertIn("pageFunction", run_input)
        self.assertNotIn("useChrome", run_input)
        self.assertNotIn("runMode", run_input)

    def test_build_run_input_keeps_web_scraper_browser_options(self) -> None:
        provider = ApifyProvider(
            settings_from_values(
                DEFAULT_VALUES
                | {
                    "apify_token": "token",
                    "apify_actor_id": "apify/web-scraper",
                    "apify_use_chrome": "true",
                }
            )
        )

        run_input = provider.build_run_input("https://old.reddit.com/comments/abc123/", "post", 1, 50)

        self.assertEqual(run_input["customData"]["actorId"], "apify/web-scraper")
        self.assertEqual(run_input["runMode"], "PRODUCTION")
        self.assertTrue(run_input["useChrome"])
        self.assertEqual(run_input["waitUntil"], ["domcontentloaded"])
        self.assertIn("maxScrollHeightPixels", run_input)

    def test_result_from_subreddit_dataset_item(self) -> None:
        provider = ApifyProvider(settings_from_values(DEFAULT_VALUES | {"apify_token": "token"}))

        result = provider.result_from_items(
            [
                {
                    "source": "old_reddit_html",
                    "scrapeType": "subreddit",
                    "loadedUrl": "https://old.reddit.com/r/python/",
                    "posts": [
                        {
                            "id": "abc123",
                            "fullname": "t3_abc123",
                            "subreddit": "python",
                            "title": "Example",
                            "author": "poster",
                            "createdAt": "2026-01-01T12:00:00+00:00",
                            "score": "42",
                            "numComments": "7",
                            "isSelf": True,
                            "over18": False,
                        }
                    ],
                }
            ]
        )

        self.assertEqual(result.stats["posts"], 1)
        self.assertEqual(result.posts[0]["id"], "abc123")
        self.assertEqual(result.posts[0]["score"], 42)
        self.assertEqual(result.posts[0]["num_comments"], 7)
        self.assertEqual(result.metadata["source"], "old_reddit_html")

    def test_result_from_post_dataset_item_with_comments(self) -> None:
        provider = ApifyProvider(settings_from_values(DEFAULT_VALUES | {"apify_token": "token"}))

        result = provider.result_from_items(
            [
                {
                    "source": "old_reddit_html",
                    "scrapeType": "post",
                    "posts": [{"id": "abc123", "title": "Example post"}],
                    "comments": [
                        {
                            "id": "c1",
                            "fullname": "t1_c1",
                            "postId": "abc123",
                            "parentId": "t3_abc123",
                            "author": "commenter",
                            "body": "Nice",
                            "score": "3",
                            "createdAt": "2026-01-01T13:00:00Z",
                        }
                    ],
                }
            ]
        )

        self.assertEqual(result.stats["posts"], 1)
        self.assertEqual(result.stats["comments"], 1)
        self.assertEqual(result.comments[0]["post_id"], "abc123")
        self.assertEqual(result.comments[0]["score"], 3)
