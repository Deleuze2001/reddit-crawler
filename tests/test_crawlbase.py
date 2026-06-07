from __future__ import annotations

import unittest
from unittest.mock import patch

from app.crawlbase import CrawlbaseClient, CrawlbaseError
from app.settings_store import DEFAULT_VALUES, settings_from_values


class CrawlbaseClientTests(unittest.TestCase):
    def test_http_error_does_not_raise_httpx_error_or_leak_token(self) -> None:
        token = "secret-token"
        settings = settings_from_values(DEFAULT_VALUES | {"crawlbase_normal_token": token})
        client = CrawlbaseClient(settings)

        with patch("app.crawlbase.httpx.Client", return_value=_FakeHttpClient()):
            result = client.fetch("https://www.reddit.com/r/test/about.json")

        self.assertEqual(result.http_status, 520)
        self.assertEqual(result.pc_status, 520)
        self.assertFalse(result.success)
        with self.assertRaises(CrawlbaseError) as raised:
            client.ensure_success(result)
        self.assertNotIn(token, str(raised.exception))


class _FakeHttpClient:
    def __enter__(self) -> "_FakeHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, *args, **kwargs) -> "_FakeResponse":
        return _FakeResponse()


class _FakeResponse:
    status_code = 520
    headers = {"content-type": "application/json"}
    text = '{"error":"upstream failure"}'


if __name__ == "__main__":
    unittest.main()
