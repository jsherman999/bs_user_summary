import tempfile
import unittest
from pathlib import Path

from backend.storage import Storage


class StorageTests(unittest.TestCase):
    def test_storage_job_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(db_path=str(Path(tmpdir) / "app.db"))
            job_id = storage.create_job("example.bsky.social")
            storage.update_job_status(job_id, "running")
            storage.set_job_result(job_id, {"ok": True}, {"raw": True})

            job = storage.get_job(job_id)
            self.assertIsNotNone(job)
            assert job is not None
            self.assertEqual(job.status, "completed")

            summary = storage.get_summary(job_id)
            self.assertEqual(summary, {"ok": True})

    def test_storage_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(db_path=str(Path(tmpdir) / "app.db"))
            storage.set_user_cache("example.bsky.social", "did:plc:test", {"value": 1})

            cached = storage.get_user_cache("example.bsky.social", max_age_seconds=3600)
            self.assertEqual(cached, {"value": 1})


if __name__ == "__main__":
    unittest.main()
