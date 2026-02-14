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

    def test_job_progress_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(db_path=str(Path(tmpdir) / "app.db"))
            job_id = storage.create_job("progress.bsky.social")
            storage.set_job_progress(
                job_id=job_id,
                stage="llm-analyze",
                message="Analyzing chunk 1 of 3",
                current=1,
                total=3,
                meta={"posts_analyzed": 20, "posts_total": 60},
            )
            job = storage.get_job(job_id)
            self.assertIsNotNone(job)
            assert job is not None
            self.assertIsNotNone(job.progress)
            assert job.progress is not None
            self.assertEqual(job.progress["stage"], "llm-analyze")
            self.assertEqual(job.progress["current"], 1)
            self.assertEqual(job.progress["total"], 3)
            self.assertEqual(job.progress["meta"]["posts_total"], 60)

    def test_mark_incomplete_jobs_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(db_path=str(Path(tmpdir) / "app.db"))
            queued = storage.create_job("queued.bsky.social")
            running = storage.create_job("running.bsky.social")
            done = storage.create_job("done.bsky.social")
            storage.update_job_status(running, "running")
            storage.set_job_result(done, {"ok": True}, {"raw": True})

            changed = storage.mark_incomplete_jobs_failed(reason="restart")
            self.assertEqual(changed, 2)

            queued_job = storage.get_job(queued)
            running_job = storage.get_job(running)
            done_job = storage.get_job(done)
            self.assertIsNotNone(queued_job)
            self.assertIsNotNone(running_job)
            self.assertIsNotNone(done_job)
            assert queued_job is not None
            assert running_job is not None
            assert done_job is not None
            self.assertEqual(queued_job.status, "failed")
            self.assertEqual(running_job.status, "failed")
            self.assertEqual(done_job.status, "completed")


if __name__ == "__main__":
    unittest.main()
