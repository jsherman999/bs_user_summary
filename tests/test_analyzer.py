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
                    "uri": "at://1",
                    "created_at": "2026-02-10T10:00:00Z",
                    "text": "I love coding and tech",
                    "is_reply": False,
                    "like_count": 2,
                    "repost_count": 1,
                    "quote_count": 0,
                    "reply_count": 3,
                },
                {
                    "uri": "at://2",
                    "created_at": "2026-02-11T11:00:00Z",
                    "text": "Replying about politics, very frustrated about policy",
                    "is_reply": True,
                    "like_count": 1,
                    "repost_count": 0,
                    "quote_count": 0,
                    "reply_count": 0,
                },
                {
                    "uri": "at://3",
                    "created_at": "2026-02-11T12:00:00Z",
                    "text": "Tech is great and developer tools are awesome",
                    "is_reply": False,
                    "like_count": 3,
                    "repost_count": 0,
                    "quote_count": 0,
                    "reply_count": 1,
                },
            ],
        }

        summary = summarize_public_history(raw_data)

        self.assertEqual(summary["metrics"]["sample_size"], 3)
        self.assertEqual(summary["metrics"]["total_posts"], 2)
        self.assertEqual(summary["metrics"]["total_replies"], 1)
        self.assertEqual(summary["metrics"]["reply_ratio"], 0.333)
        self.assertEqual(summary["metrics"]["total_visible_reactions"], 11)
        self.assertTrue(summary["top_topics"])
        self.assertTrue(summary["claims"])
        self.assertTrue(summary["evidence"])

    def test_claims_are_grounded_in_evidence(self) -> None:
        raw_data = {
            "handle": "grounded.bsky.social",
            "did": "did:plc:test",
            "profile": {"handle": "grounded.bsky.social"},
            "feed_items": [
                {
                    "uri": "at://1",
                    "created_at": "2026-02-10T10:00:00Z",
                    "text": "policy discussion",
                    "is_reply": True,
                    "like_count": 0,
                    "repost_count": 0,
                    "quote_count": 0,
                    "reply_count": 0,
                },
                {
                    "uri": "at://2",
                    "created_at": "2026-02-10T11:00:00Z",
                    "text": "more policy discussion",
                    "is_reply": False,
                    "like_count": 0,
                    "repost_count": 0,
                    "quote_count": 0,
                    "reply_count": 0,
                },
            ],
        }

        summary = summarize_public_history(raw_data)
        evidence_ids = {entry["id"] for entry in summary["evidence"]}

        for claim in summary["claims"]:
            self.assertTrue(claim["evidence_ids"])
            self.assertTrue(set(claim["evidence_ids"]).issubset(evidence_ids))


if __name__ == "__main__":
    unittest.main()
