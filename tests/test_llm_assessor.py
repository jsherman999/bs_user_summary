import unittest

from backend.llm_assessor import assess_topic_alignment


class LLMAssessorTests(unittest.TestCase):
    def test_disabled_returns_deterministic_fallback(self) -> None:
        result = assess_topic_alignment(
            evidence=[{"id": "ev1", "text": "test", "is_reply": False}],
            top_topics=[{"topic": "technology", "count": 7}],
            takes=[
                {
                    "topic": "technology",
                    "stance": "mostly supportive",
                    "confidence": 0.8,
                    "evidence_ids": ["ev1"],
                }
            ],
            options={"enabled": False},
        )

        self.assertEqual(result["source"], "deterministic_fallback")
        self.assertEqual(result["status"], "disabled")

    def test_provider_none_returns_deterministic_fallback(self) -> None:
        result = assess_topic_alignment(
            evidence=[{"id": "ev1", "text": "test", "is_reply": False}],
            top_topics=[{"topic": "technology", "count": 7}],
            takes=[
                {
                    "topic": "technology",
                    "stance": "mostly supportive",
                    "confidence": 0.8,
                    "evidence_ids": ["ev1"],
                }
            ],
            options={"enabled": True, "provider": "none"},
        )

        self.assertEqual(result["source"], "deterministic_fallback")
        self.assertEqual(result["status"], "fallback")

    def test_provider_none_fallback_handles_politics_topic(self) -> None:
        result = assess_topic_alignment(
            evidence=[
                {"id": "ev1", "text": "Election policy and senate vote updates", "is_reply": False},
                {"id": "ev2", "text": "Government regulation debate", "is_reply": True},
            ],
            top_topics=[{"topic": "politics", "count": 4}],
            takes=[],
            options={"enabled": True, "provider": "none"},
        )
        topics = [entry["topic"] for entry in result["topic_alignments"]]
        self.assertIn("politics", topics)


if __name__ == "__main__":
    unittest.main()
