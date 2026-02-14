# BlueSky User Summary

A mobile-friendly web app for summarizing a BlueSky user's public post and reply history with transparent, evidence-linked metrics.

## What It Does
- Accepts a BlueSky handle (public account).
- Fetches public profile + recent public feed items from BlueSky's public API.
- Computes deterministic metrics:
  - posts vs replies
  - activity pace
  - top terms
  - top topic clusters (keyword based)
- Produces grounded narrative output:
  - claim objects with confidence and evidence IDs
  - topic takes with uncertainty notes
  - honesty notes about data boundaries
- Adds time-window comparison (recent window vs prior window).
- Supports summary export in JSON and Markdown formats.
- Exposes observability stats and retention cleanup endpoints.
- Presents all results in a mobile-first UI, including evidence and comparison panels.
- Stores job results and cache locally in SQLite.

## Project Structure
- `backend/server.py` HTTP server and API routes
- `backend/bluesky_client.py` BlueSky public API client
- `backend/analyzer.py` deterministic summarization logic + evidence linking + comparison
- `backend/storage.py` SQLite persistence for jobs/cache + cleanup
- `frontend/` static mobile-friendly web app
- `docs/` project documentation
- `tests/` unit tests

## Requirements
- macOS or Linux
- Python 3.11+

## Run Locally (LAN Accessible)
```bash
python3 -m backend.server --host 0.0.0.0 --port 8080
```

Then open:
- local machine: `http://127.0.0.1:8080`
- LAN device: `http://<your-mac-lan-ip>:8080`

To find LAN IP on macOS:
```bash
ipconfig getifaddr en0
```

## API Endpoints (Phase 3)
- `GET /api/health`
- `POST /api/analyze`
  - body: `{ "handle": "alice.bsky.social", "max_items": 200, "comparison_window_days": 30, "use_cache": true }`
- `GET /api/jobs/{job_id}`
- `GET /api/summary/{job_id}`
- `GET /api/export/{job_id}.json`
- `GET /api/export/{job_id}.md`
- `GET /api/stats`
- `POST /api/maintenance/cleanup`
- `GET /api/user/raw?handle=alice.bsky.social`

See `docs/api.md` for full payload examples.

## Tests
```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Data and Privacy
- Uses public BlueSky data only.
- No private account access.
- Caches fetched public data and summaries in local SQLite at `data/app.db`.
- Cleanup endpoint can delete old cache/job records by age.

## Roadmap Status
- Phase 1: done
- Phase 2: done
- Phase 3: done

Detailed task breakdown: `docs/task-breakdown.md`
