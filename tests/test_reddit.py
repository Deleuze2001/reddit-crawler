from __future__ import annotations

import unittest

from app import reddit


class RedditUrlTests(unittest.TestCase):
    def test_clean_subreddit_accepts_names_and_urls(self) -> None:
        self.assertEqual(reddit.clean_subreddit("python"), "python")
        self.assertEqual(reddit.clean_subreddit("r/Python"), "Python")
        self.assertEqual(reddit.clean_subreddit("https://www.reddit.com/r/python/top/"), "python")

    def test_extract_post_id_accepts_url_or_id(self) -> None:
        self.assertEqual(reddit.extract_post_id("abc123"), "abc123")
        self.assertEqual(
            reddit.extract_post_id("https://www.reddit.com/r/python/comments/abc123/example/"),
            "abc123",
        )

    def test_search_url_can_be_scoped_to_subreddit(self) -> None:
        url = reddit.search_url("crawlbase", "relevance", 10, subreddit="python")
        self.assertIn("https://www.reddit.com/r/python/search.json", url)
        self.assertIn("restrict_sr=1", url)
        self.assertIn("q=crawlbase", url)


class RedditParserTests(unittest.TestCase):
    def test_parse_listing_posts_extracts_core_fields(self) -> None:
        posts = reddit.parse_listing_posts(_listing_payload())

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["id"], "abc123")
        self.assertEqual(posts[0]["subreddit"], "python")
        self.assertEqual(posts[0]["score"], 42)
        self.assertEqual(posts[0]["permalink"], "https://www.reddit.com/r/python/comments/abc123/example/")

    def test_parse_thread_walks_nested_comments(self) -> None:
        posts, comments = reddit.parse_post_thread([_listing_payload(), _comments_payload()])

        self.assertEqual(posts[0]["id"], "abc123")
        self.assertEqual([comment["id"] for comment in comments], ["c1", "c2"])
        self.assertEqual(comments[0]["post_id"], "abc123")
        self.assertEqual(comments[1]["parent_id"], "t1_c1")

    def test_parse_about_payloads(self) -> None:
        subreddit = reddit.parse_subreddit_about(
            {"kind": "t5", "data": {"display_name": "python", "subscribers": 1234}}
        )
        user = reddit.parse_user_about(
            {
                "kind": "t2",
                "data": {
                    "name": "example_user",
                    "link_karma": 5,
                    "comment_karma": 7,
                    "subreddit": {"display_name_prefixed": "u/example_user"},
                },
            }
        )

        self.assertEqual(subreddit["name"], "python")
        self.assertEqual(subreddit["subscribers"], 1234)
        self.assertEqual(user["username"], "example_user")
        self.assertEqual(user["total_karma"], 12)


def _listing_payload() -> dict:
    return {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "abc123",
                        "name": "t3_abc123",
                        "subreddit": "python",
                        "title": "Example",
                        "author": "author",
                        "selftext": "Body",
                        "url": "https://www.reddit.com/r/python/comments/abc123/example/",
                        "permalink": "/r/python/comments/abc123/example/",
                        "created_utc": 1_700_000_000,
                        "score": 42,
                        "upvote_ratio": 0.97,
                        "num_comments": 2,
                        "is_self": True,
                        "over_18": False,
                    },
                }
            ]
        },
    }


def _comments_payload() -> dict:
    return {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t1",
                    "data": {
                        "id": "c1",
                        "name": "t1_c1",
                        "parent_id": "t3_abc123",
                        "author": "commenter",
                        "body": "First",
                        "score": 9,
                        "created_utc": 1_700_000_100,
                        "replies": {
                            "kind": "Listing",
                            "data": {
                                "children": [
                                    {
                                        "kind": "t1",
                                        "data": {
                                            "id": "c2",
                                            "name": "t1_c2",
                                            "parent_id": "t1_c1",
                                            "author": "reply",
                                            "body": "Nested",
                                            "score": 2,
                                            "created_utc": 1_700_000_200,
                                            "replies": "",
                                        },
                                    }
                                ]
                            },
                        },
                    },
                }
            ]
        },
    }


if __name__ == "__main__":
    unittest.main()
