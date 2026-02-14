import unittest

from backend.analyzer import summarize_public_history


class AnalyzerTests(unittest.TestCase):
    def test_summarize_public_history_counts_posts_and_replies(self) -> None:
        raw_data = {
            "handle": "example.bsky.social",
            "did": "did:plc:test",
            "profile": {"handle": "example.bsky.social"},
            "feed_items": [
                {
                    "created_at": "2026-02-10T10:00:00Z",
                    "text": "I love coding and tech",
                    "is_reply": False,
                    "like_count": 2,
                    "repost_count": 1,
                    "quote_count": 0,
                    "reply_count": 3,
                },
                {
                    "created_at": "2026-02-11T11:00:00Z",
                    "text": "Replying about politics",
                    "is_reply": True,
                    "like_count": 1,
                    "repost_count": 0,
                    "quote_count": 0,
                    "reply_count": 0,
                },
            ],
        }

        summary = summarize_public_history(raw_data)

        self.assertEqual(summary["metrics"]["sample_size"], 2)
        self.assertEqual(summary["metrics"]["total_posts"], 1)
        self.assertEqual(summary["metrics"]["total_replies"], 1)
        self.assertEqual(summary["metrics"]["reply_ratio"], 0.5)
        self.assertEqual(summary["metrics"]["total_visible_reactions"], 7)
        self.assertTrue(summary["top_topics"])


if __name__ == "__main__":
    unittest.main()
