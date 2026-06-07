from __future__ import annotations

import unittest

from app import settings_store


class SettingsStoreTests(unittest.TestCase):
    def test_settings_from_values_bounds_and_normalizes(self) -> None:
        settings = settings_store.settings_from_values(
            {
                "app_title": "  Custom Crawler  ",
                "crawlbase_normal_token": " normal ",
                "crawlbase_js_token": "",
                "crawlbase_country": "gb",
                "crawlbase_device": "mobile",
                "crawlbase_timeout_seconds": "10",
                "crawlbase_rate_limit_seconds": "99",
                "collector_poll_seconds": "0",
                "reddit_default_limit": "50",
                "reddit_max_limit": "20",
            }
        )

        self.assertEqual(settings.app_title, "Custom Crawler")
        self.assertEqual(settings.crawlbase_normal_token, "normal")
        self.assertIsNone(settings.crawlbase_js_token)
        self.assertEqual(settings.crawlbase_country, "GB")
        self.assertEqual(settings.crawlbase_device, "mobile")
        self.assertEqual(settings.crawlbase_timeout_seconds, 30.0)
        self.assertEqual(settings.crawlbase_rate_limit_seconds, 60.0)
        self.assertEqual(settings.collector_poll_seconds, 1.0)
        self.assertEqual(settings.reddit_max_limit, 20)
        self.assertEqual(settings.reddit_default_limit, 20)

    def test_public_settings_masks_token_values(self) -> None:
        settings = settings_store.settings_from_values(
            settings_store.DEFAULT_VALUES
            | {
                "crawlbase_normal_token": "secret-token",
                "crawlbase_js_token": "js-secret",
            }
        )

        public = settings_store.public_settings(settings)

        self.assertTrue(public["crawlbase_normal_token_saved"])
        self.assertTrue(public["crawlbase_js_token_saved"])
        self.assertNotIn("secret-token", public.values())
        self.assertNotIn("js-secret", public.values())


if __name__ == "__main__":
    unittest.main()
