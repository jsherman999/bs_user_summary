import sqlite3
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

    def test_cleanup_old_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "app.db"
            storage = Storage(db_path=str(db_path))

            job_id = storage.create_job("cleanup.bsky.social")
            storage.set_job_result(job_id, {"ok": True}, {"raw": True})
            storage.set_user_cache("cleanup.bsky.social", "did:plc:test", {"value": 1})

            with sqlite3.connect(db_path) as conn:
                conn.execute("UPDATE jobs SET updated_at = 1 WHERE id = ?", (job_id,))
                conn.execute("UPDATE user_cache SET fetched_at = 1 WHERE handle = ?", ("cleanup.bsky.social",))
                conn.commit()

            result = storage.cleanup_old_data(max_age_seconds=5)
            self.assertGreaterEqual(result["jobs_deleted"], 1)
            self.assertGreaterEqual(result["cache_deleted"], 1)

    def test_job_status_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(db_path=str(Path(tmpdir) / "app.db"))
            storage.create_job("count1.bsky.social")
            storage.create_job("count2.bsky.social")
            counts = storage.get_job_status_counts()
            self.assertEqual(counts["queued"], 2)
            self.assertEqual(counts["total"], 2)


if __name__ == "__main__":
    unittest.main()
