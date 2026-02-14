from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class JobRecord:
    id: int
    handle: str
    status: str
    created_at: int
    updated_at: int
    error: str | None
    summary: dict[str, Any] | None
    progress: dict[str, Any] | None


class Storage:
    def __init__(self, db_path: str = "data/app.db") -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure the file exists before opening connection URI in rwc mode.
        self.db_path.touch(exist_ok=True)
        last_error: sqlite3.OperationalError | None = None
        db_uri = f"file:{self.db_path}?mode=rwc"
        for attempt in range(1, 11):
            try:
                conn = sqlite3.connect(db_uri, uri=True, timeout=10)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA busy_timeout = 5000")
                return conn
            except sqlite3.OperationalError as exc:
                last_error = exc
                # Retry transient open failures before bubbling up.
                time.sleep(min(1.0, 0.05 * attempt))
        if last_error is not None:
            raise sqlite3.OperationalError(
                f"unable to open database file at {self.db_path}: {last_error}"
            )
        raise sqlite3.OperationalError(f"unable to open database file at {self.db_path}")

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    handle TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    error TEXT,
                    summary_json TEXT,
                    raw_json TEXT,
                    progress_json TEXT
                )
                """
            )
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "progress_json" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN progress_json TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_cache (
                    handle TEXT PRIMARY KEY,
                    did TEXT NOT NULL,
                    fetched_at INTEGER NOT NULL,
                    raw_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def create_job(self, handle: str) -> int:
        now = int(time.time())
        progress = {
            "stage": "queued",
            "message": "Job queued",
            "current": 0,
            "total": 0,
            "percent": 0.0,
        }
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (handle, status, created_at, updated_at, progress_json) VALUES (?, ?, ?, ?, ?)",
                (handle, "queued", now, now, json.dumps(progress)),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def update_job_status(self, job_id: int, status: str, error: str | None = None) -> None:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, error, now, job_id),
            )
            conn.commit()

    def set_job_result(self, job_id: int, summary: dict[str, Any], raw_data: dict[str, Any]) -> None:
        now = int(time.time())
        progress = {
            "stage": "completed",
            "message": "Analysis completed",
            "current": 1,
            "total": 1,
            "percent": 100.0,
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, summary_json = ?, raw_json = ?, progress_json = ?, error = NULL, updated_at = ?
                WHERE id = ?
                """,
                ("completed", json.dumps(summary), json.dumps(raw_data), json.dumps(progress), now, job_id),
            )
            conn.commit()

    def set_job_progress(
        self,
        job_id: int,
        stage: str,
        message: str,
        current: int,
        total: int,
        meta: dict[str, Any] | None = None,
    ) -> None:
        now = int(time.time())
        current = max(0, int(current))
        total = max(0, int(total))
        if total <= 0:
            percent = 0.0
        else:
            percent = round(min(100.0, max(0.0, (current / total) * 100.0)), 1)

        progress = {
            "stage": stage,
            "message": message,
            "current": current,
            "total": total,
            "percent": percent,
            "meta": meta or {},
            "updated_at": now,
        }

        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET progress_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(progress), now, job_id),
            )
            conn.commit()

    def get_job(self, job_id: int) -> JobRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        summary = json.loads(row["summary_json"]) if row["summary_json"] else None
        progress = json.loads(row["progress_json"]) if row["progress_json"] else None
        return JobRecord(
            id=int(row["id"]),
            handle=str(row["handle"]),
            status=str(row["status"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            error=row["error"],
            summary=summary,
            progress=progress,
        )

    def get_summary(self, job_id: int) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT summary_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None or row["summary_json"] is None:
            return None
        return json.loads(row["summary_json"])

    def set_user_cache(self, handle: str, did: str, raw_data: dict[str, Any]) -> None:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_cache (handle, did, fetched_at, raw_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(handle)
                DO UPDATE SET did=excluded.did, fetched_at=excluded.fetched_at, raw_json=excluded.raw_json
                """,
                (handle, did, now, json.dumps(raw_data)),
            )
            conn.commit()

    def get_user_cache(self, handle: str, max_age_seconds: int) -> dict[str, Any] | None:
        oldest_allowed = int(time.time()) - max_age_seconds
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT raw_json FROM user_cache WHERE handle = ? AND fetched_at >= ?",
                (handle, oldest_allowed),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["raw_json"])

    def get_raw_for_handle(self, handle: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT raw_json FROM user_cache WHERE handle = ?", (handle,)).fetchone()
        if row is None:
            return None
        return json.loads(row["raw_json"])

    def get_job_status_counts(self) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status").fetchall()
        counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
        for row in rows:
            counts[str(row["status"])] = int(row["count"])
        counts["total"] = sum(counts.values())
        return counts

    def get_cache_count(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM user_cache").fetchone()
        return int(row["count"]) if row else 0

    def cleanup_old_data(self, max_age_seconds: int) -> dict[str, int]:
        cutoff = int(time.time()) - max_age_seconds
        with self._lock, self._connect() as conn:
            jobs_deleted = conn.execute(
                "DELETE FROM jobs WHERE updated_at < ? AND status IN ('completed', 'failed')",
                (cutoff,),
            ).rowcount
            cache_deleted = conn.execute(
                "DELETE FROM user_cache WHERE fetched_at < ?",
                (cutoff,),
            ).rowcount
            conn.commit()
        return {
            "jobs_deleted": int(jobs_deleted or 0),
            "cache_deleted": int(cache_deleted or 0),
            "cutoff_epoch": cutoff,
        }

    def mark_incomplete_jobs_failed(self, reason: str = "Server restarted during analysis") -> int:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE jobs
                SET status = 'failed',
                    error = COALESCE(error, ?),
                    updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (reason, now),
            ).rowcount
            conn.commit()
        return int(updated or 0)
