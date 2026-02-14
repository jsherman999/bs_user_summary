from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import mimetypes
import os
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.analyzer import summarize_public_history
from backend.bluesky_client import BlueSkyClient, BlueSkyError, FetchOptions
from backend.storage import Storage


LOGGER = logging.getLogger("bs_user_summary")
STORAGE = Storage()
CLIENT = BlueSkyClient()
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)
FRONTEND_ROOT = Path(__file__).resolve().parent.parent / "frontend"


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length_header = handler.headers.get("Content-Length", "0")
    try:
        content_length = int(length_header)
    except ValueError:
        content_length = 0
    raw = handler.rfile.read(content_length) if content_length > 0 else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _normalize_handle(raw: str) -> str:
    return raw.strip().lstrip("@").lower()


def _run_job(job_id: int, handle: str, max_items: int, use_cache: bool, cache_age_s: int) -> None:
    STORAGE.update_job_status(job_id, "running")
    try:
        options = FetchOptions(max_items=max_items)
        raw_data = None

        if use_cache:
            raw_data = STORAGE.get_user_cache(handle, max_age_seconds=cache_age_s)
            if raw_data is not None:
                LOGGER.info("Using cache for @%s (job=%s)", handle, job_id)

        if raw_data is None:
            raw_data = CLIENT.fetch_public_history(handle, options=options)
            STORAGE.set_user_cache(handle, raw_data.get("did") or "", raw_data)

        summary = summarize_public_history(raw_data)
        STORAGE.set_job_result(job_id, summary=summary, raw_data=raw_data)
        LOGGER.info("Completed job %s for @%s", job_id, handle)
    except BlueSkyError as exc:
        STORAGE.update_job_status(job_id, "failed", error=str(exc))
        LOGGER.error("BlueSky error for job %s: %s", job_id, exc)
    except Exception as exc:  # noqa: BLE001
        STORAGE.update_job_status(job_id, "failed", error=str(exc))
        LOGGER.error("Unhandled error for job %s: %s\n%s", job_id, exc, traceback.format_exc())


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "BSUserSummary/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            _json_response(self, HTTPStatus.OK, {"ok": True, "service": "bs-user-summary"})
            return

        if path.startswith("/api/jobs/"):
            job_id_text = path.removeprefix("/api/jobs/")
            if not job_id_text.isdigit():
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid job id"})
                return
            job = STORAGE.get_job(int(job_id_text))
            if job is None:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Job not found"})
                return
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "id": job.id,
                    "handle": job.handle,
                    "status": job.status,
                    "created_at": job.created_at,
                    "updated_at": job.updated_at,
                    "error": job.error,
                },
            )
            return

        if path.startswith("/api/summary/"):
            job_id_text = path.removeprefix("/api/summary/")
            if not job_id_text.isdigit():
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid job id"})
                return
            summary = STORAGE.get_summary(int(job_id_text))
            if summary is None:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Summary not available"})
                return
            _json_response(self, HTTPStatus.OK, summary)
            return

        if path == "/api/user/raw":
            query = parse_qs(parsed.query)
            handle = _normalize_handle((query.get("handle") or [""])[0])
            if not handle:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Missing handle"})
                return
            raw_data = STORAGE.get_raw_for_handle(handle)
            if raw_data is None:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "No cached data for handle"})
                return
            _json_response(self, HTTPStatus.OK, raw_data)
            return

        self._serve_frontend(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/api/analyze":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body"})
                return

            handle = _normalize_handle(str(body.get("handle") or ""))
            if not handle:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "handle is required"})
                return

            max_items = int(body.get("max_items") or 200)
            max_items = max(25, min(max_items, 500))
            use_cache = bool(body.get("use_cache", True))
            cache_age_s = int(body.get("cache_age_seconds") or 900)
            cache_age_s = max(60, min(cache_age_s, 86400))

            job_id = STORAGE.create_job(handle=handle)
            EXECUTOR.submit(_run_job, job_id, handle, max_items, use_cache, cache_age_s)

            _json_response(
                self,
                HTTPStatus.ACCEPTED,
                {
                    "job_id": job_id,
                    "status": "queued",
                    "handle": handle,
                },
            )
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        LOGGER.info("%s - %s", self.address_string(), fmt % args)

    def _serve_frontend(self, path: str) -> None:
        if path == "/":
            rel_path = "index.html"
        else:
            rel_path = path.lstrip("/")

        requested = (FRONTEND_ROOT / rel_path).resolve()
        if FRONTEND_ROOT not in requested.parents and requested != FRONTEND_ROOT:
            self.send_error(HTTPStatus.FORBIDDEN)
            return

        if not requested.exists() or not requested.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        mime_type, _ = mimetypes.guess_type(str(requested))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        file_size = requested.stat().st_size
        self.send_header("Content-Length", str(file_size))
        self.end_headers()
        with requested.open("rb") as file_obj:
            self.wfile.write(file_obj.read())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BlueSky user summary server")
    parser.add_argument("--host", default=os.getenv("BS_APP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("BS_APP_PORT", "8080")))
    parser.add_argument("--log-level", default=os.getenv("BS_APP_LOG_LEVEL", "INFO"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    httpd = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    LOGGER.info("Serving on http://%s:%s", args.host, args.port)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Shutting down...")
    finally:
        EXECUTOR.shutdown(wait=False, cancel_futures=True)
        httpd.server_close()


if __name__ == "__main__":
    main()
