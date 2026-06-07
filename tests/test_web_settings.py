from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from starlette.testclient import TestClient

from app import settings_store
from app.web import app


class WebSettingsTests(unittest.TestCase):
    def test_settings_page_masks_saved_tokens(self) -> None:
        runtime = settings_store.settings_from_values(
            settings_store.DEFAULT_VALUES
            | {
                "crawlbase_normal_token": "normal-secret",
                "crawlbase_js_token": "js-secret",
            }
        )

        with _patched_connection(), patch("app.web.settings_store.get_crawler_settings", return_value=runtime):
            response = TestClient(app).get("/settings")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Saved", response.text)
        self.assertNotIn("normal-secret", response.text)
        self.assertNotIn("js-secret", response.text)

    def test_settings_post_saves_tokens(self) -> None:
        captured: dict[str, str] = {}

        def capture_update(conn, updates):
            captured.update(updates)

        with _patched_connection(), patch("app.web.settings_store.update_crawler_settings", side_effect=capture_update):
            response = TestClient(app).post(
                "/settings",
                data={
                    "app_title": "Test Crawler",
                    "crawlbase_normal_token": "normal-secret",
                    "crawlbase_js_token": "js-secret",
                    "crawlbase_country": "GB",
                    "crawlbase_device": "desktop",
                    "crawlbase_timeout_seconds": "95",
                    "crawlbase_rate_limit_seconds": "1.5",
                    "collector_poll_seconds": "5",
                    "reddit_default_limit": "10",
                    "reddit_max_limit": "20",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/settings?saved=1")
        self.assertEqual(captured["crawlbase_normal_token"], "normal-secret")
        self.assertEqual(captured["crawlbase_js_token"], "js-secret")
        self.assertEqual(captured["crawlbase_country"], "GB")


@contextmanager
def _dummy_connection(*args, **kwargs):
    yield object()


def _patched_connection():
    return patch("app.web.database.connection", side_effect=_dummy_connection)


if __name__ == "__main__":
    unittest.main()
