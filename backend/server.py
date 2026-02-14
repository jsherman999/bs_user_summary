from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import mimetypes
import os
import time
import traceback
from collections import defaultdict
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
START_TIME = int(time.time())
REQUEST_COUNTS: defaultdict[str, int] = defaultdict(int)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, status: int, text: str, content_type: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
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


def _summary_to_markdown(summary: dict) -> str:
    user = summary.get("user") or {}
    metrics = summary.get("metrics") or {}
    claims = summary.get("claims") or []
    takes = summary.get("takes") or []
    llm_assessment = summary.get("llm_assessment") or {}
    uncertainty = summary.get("uncertainty_notes") or []
    comparison = summary.get("comparison") or {}

    lines = [
        f"# BlueSky Summary Report: @{user.get('handle', 'unknown')}",
        "",
        f"Generated at: {summary.get('generated_at', 'unknown')}",
        "",
        "## Narrative Summary",
        summary.get("summary_text") or "No narrative summary.",
        "",
        "## Core Metrics",
        f"- Sample size: {metrics.get('sample_size', 0)}",
        f"- Posts: {metrics.get('total_posts', 0)}",
        f"- Replies: {metrics.get('total_replies', 0)}",
        f"- Reply ratio: {metrics.get('reply_ratio', 0)}",
        f"- Active days: {metrics.get('active_days', 0)}",
        "",
        "## Claims",
    ]

    if claims:
        for claim in claims:
            lines.append(
                f"- {claim.get('text')} (confidence {claim.get('confidence')}, evidence: {', '.join(claim.get('evidence_ids') or [])})"
            )
    else:
        lines.append("- No grounded claims available.")

    lines.extend(["", "## Topic Takes"])
    if takes:
        for take in takes:
            lines.append(
                f"- {take.get('statement')} (confidence {take.get('confidence')}, mentions {take.get('signal_count')})"
            )
    else:
        lines.append("- No strong topic takes in sample.")

    lines.extend(["", "## LLM Alignment"])
    llm_alignments = llm_assessment.get("topic_alignments") or []
    lines.append(
        f"- Source: {llm_assessment.get('source', 'unknown')} ({llm_assessment.get('provider', 'n/a')}:{llm_assessment.get('model', 'default')})"
    )
    if llm_alignments:
        for row in llm_alignments[:6]:
            lines.append(
                f"- {row.get('topic')}: {row.get('alignment')} (confidence {row.get('confidence')}, mentions {row.get('mention_count')})"
            )
    else:
        lines.append("- No LLM alignments available.")

    lines.extend(["", "## Comparison"])
    if comparison:
        recent = comparison.get("recent_window") or {}
        prior = comparison.get("prior_window") or {}
        delta = comparison.get("delta") or {}
        lines.append(f"- Window days: {comparison.get('window_days')}")
        lines.append(f"- Recent items: {recent.get('items', 0)}")
        lines.append(f"- Prior items: {prior.get('items', 0)}")
        lines.append(f"- Delta items: {delta.get('items', 0)}")
        lines.append(f"- Activity direction: {delta.get('activity_direction', 'flat')}")
    else:
        lines.append("- Not enough timestamped data for comparison.")

    lines.extend(["", "## Uncertainty Notes"])
    if uncertainty:
        for note in uncertainty:
            lines.append(f"- {note}")
    else:
        lines.append("- No additional uncertainty notes.")

    return "\n".join(lines)


def _run_job(
    job_id: int,
    handle: str,
    max_items: int,
    use_cache: bool,
    cache_age_s: int,
    comparison_window_days: int,
    llm_options: dict[str, Any],
) -> None:
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

        summary = summarize_public_history(
            raw_data, comparison_window_days=comparison_window_days, llm_options=llm_options
        )
        STORAGE.set_job_result(job_id, summary=summary, raw_data=raw_data)
        LOGGER.info("Completed job %s for @%s", job_id, handle)
    except BlueSkyError as exc:
        STORAGE.update_job_status(job_id, "failed", error=str(exc))
        LOGGER.error("BlueSky error for job %s: %s", job_id, exc)
    except Exception as exc:  # noqa: BLE001
        STORAGE.update_job_status(job_id, "failed", error=str(exc))
        LOGGER.error("Unhandled error for job %s: %s\n%s", job_id, exc, traceback.format_exc())


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "BSUserSummary/0.3"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        REQUEST_COUNTS[f"GET {path}"] += 1

        if path == "/api/health":
            _json_response(self, HTTPStatus.OK, {"ok": True, "service": "bs-user-summary"})
            return

        if path == "/api/stats":
            now = int(time.time())
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "uptime_seconds": now - START_TIME,
                    "started_at": START_TIME,
                    "job_counts": STORAGE.get_job_status_counts(),
                    "cache_entries": STORAGE.get_cache_count(),
                    "request_counts": dict(sorted(REQUEST_COUNTS.items())),
                },
            )
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

        if path.startswith("/api/export/"):
            suffix = path.removeprefix("/api/export/")
            if suffix.endswith(".json"):
                job_id_text = suffix[: -len(".json")]
                if not job_id_text.isdigit():
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid job id"})
                    return
                summary = STORAGE.get_summary(int(job_id_text))
                if summary is None:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Summary not available"})
                    return
                _json_response(self, HTTPStatus.OK, summary)
                return
            if suffix.endswith(".md"):
                job_id_text = suffix[: -len(".md")]
                if not job_id_text.isdigit():
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid job id"})
                    return
                summary = STORAGE.get_summary(int(job_id_text))
                if summary is None:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Summary not available"})
                    return
                report_md = _summary_to_markdown(summary)
                _text_response(self, HTTPStatus.OK, report_md, "text/markdown; charset=utf-8")
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
        path = parsed.path
        REQUEST_COUNTS[f"POST {path}"] += 1

        if path == "/api/analyze":
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
            comparison_window_days = int(body.get("comparison_window_days") or 30)
            comparison_window_days = max(7, min(comparison_window_days, 90))
            llm_enabled = bool(body.get("enable_llm", True))
            llm_provider = str(body.get("llm_provider") or os.getenv("BS_LLM_PROVIDER", "auto")).strip().lower()
            llm_model = str(body.get("llm_model") or os.getenv("BS_LLM_MODEL", "")).strip()
            llm_max_posts = int(body.get("llm_max_posts") or os.getenv("BS_LLM_MAX_POSTS", "500"))
            llm_max_posts = max(25, min(llm_max_posts, 500))

            llm_options = {
                "enabled": llm_enabled,
                "provider": llm_provider,
                "model": llm_model,
                "max_posts": llm_max_posts,
            }

            job_id = STORAGE.create_job(handle=handle)
            EXECUTOR.submit(
                _run_job,
                job_id,
                handle,
                max_items,
                use_cache,
                cache_age_s,
                comparison_window_days,
                llm_options,
            )

            _json_response(
                self,
                HTTPStatus.ACCEPTED,
                {
                    "job_id": job_id,
                    "status": "queued",
                    "handle": handle,
                    "comparison_window_days": comparison_window_days,
                    "llm_enabled": llm_enabled,
                    "llm_provider": llm_provider,
                    "llm_model": llm_model or None,
                },
            )
            return

        if path == "/api/maintenance/cleanup":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body"})
                return

            max_age_days = int(body.get("max_age_days") or 30)
            max_age_days = max(1, min(max_age_days, 365))
            cleanup = STORAGE.cleanup_old_data(max_age_seconds=max_age_days * 86400)
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "max_age_days": max_age_days,
                    **cleanup,
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
