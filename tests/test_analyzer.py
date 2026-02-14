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
        self.assertIn("llm_assessment", summary)

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

    def test_comparison_window_present_with_timestamped_data(self) -> None:
        raw_data = {
            "handle": "compare.bsky.social",
            "did": "did:plc:test",
            "profile": {"handle": "compare.bsky.social"},
            "feed_items": [
                {"uri": "at://1", "created_at": "2026-01-01T10:00:00Z", "text": "older", "is_reply": False},
                {"uri": "at://2", "created_at": "2026-01-15T10:00:00Z", "text": "older 2", "is_reply": True},
                {"uri": "at://3", "created_at": "2026-02-01T10:00:00Z", "text": "recent", "is_reply": False},
                {"uri": "at://4", "created_at": "2026-02-10T10:00:00Z", "text": "recent 2", "is_reply": True},
            ],
        }

        summary = summarize_public_history(raw_data, comparison_window_days=20)

        self.assertIn("comparison", summary)
        self.assertIsNotNone(summary["comparison"])
        assert summary["comparison"] is not None
        self.assertEqual(summary["comparison"]["window_days"], 20)

    def test_top_terms_filter_platform_noise_and_mentions(self) -> None:
        raw_data = {
            "handle": "noise.bsky.social",
            "did": "did:plc:test",
            "profile": {"handle": "noise.bsky.social"},
            "feed_items": [
                {
                    "uri": "at://1",
                    "created_at": "2026-02-10T10:00:00Z",
                    "text": "https://bsky.app/profile/noise.bsky.social/post/abc nice thread @someone",
                    "is_reply": False,
                },
                {
                    "uri": "at://2",
                    "created_at": "2026-02-10T10:05:00Z",
                    "text": "Real topic value security security",
                    "is_reply": False,
                },
            ],
        }

        summary = summarize_public_history(raw_data)
        terms = {entry["term"] for entry in summary["top_terms"]}
        self.assertIn("security", terms)
        self.assertNotIn("bsky", terms)
        self.assertNotIn("app", terms)
        self.assertNotIn("profile", terms)

    def test_takes_require_minimum_signal_volume(self) -> None:
        raw_data = {
            "handle": "sparse.bsky.social",
            "did": "did:plc:test",
            "profile": {"handle": "sparse.bsky.social"},
            "feed_items": [
                {"uri": "at://1", "created_at": "2026-02-10T10:00:00Z", "text": "policy", "is_reply": False},
                {"uri": "at://2", "created_at": "2026-02-10T10:05:00Z", "text": "policy", "is_reply": False},
                {"uri": "at://3", "created_at": "2026-02-10T10:10:00Z", "text": "policy", "is_reply": False},
                {"uri": "at://4", "created_at": "2026-02-10T10:15:00Z", "text": "policy", "is_reply": False},
            ],
        }

        summary = summarize_public_history(raw_data)
        self.assertEqual(summary["takes"], [])
        self.assertTrue(summary["uncertainty_notes"])

    def test_llm_provider_none_uses_fallback(self) -> None:
        raw_data = {
            "handle": "fallback.bsky.social",
            "did": "did:plc:test",
            "profile": {"handle": "fallback.bsky.social"},
            "feed_items": [
                {"uri": "at://1", "created_at": "2026-02-10T10:00:00Z", "text": "technology and code", "is_reply": False},
                {"uri": "at://2", "created_at": "2026-02-10T10:05:00Z", "text": "technology and software", "is_reply": False},
                {"uri": "at://3", "created_at": "2026-02-10T10:10:00Z", "text": "technology and dev", "is_reply": False},
                {"uri": "at://4", "created_at": "2026-02-10T10:15:00Z", "text": "technology and app", "is_reply": False},
                {"uri": "at://5", "created_at": "2026-02-10T10:20:00Z", "text": "technology and ai", "is_reply": False},
            ],
        }

        summary = summarize_public_history(raw_data, llm_options={"enabled": True, "provider": "none"})
        self.assertEqual(summary["llm_assessment"]["source"], "deterministic_fallback")


if __name__ == "__main__":
    unittest.main()
