# BlueSky User Summary

A mobile-friendly web app for summarizing a BlueSky user's public post and reply history with transparent, evidence-oriented metrics.

## What It Does
- Accepts a BlueSky handle (public account).
- Fetches public profile + recent public feed items from BlueSky's public API.
- Computes deterministic metrics:
  - posts vs replies
  - activity pace
  - top terms
  - top topic clusters (keyword based)
- Presents summary in a mobile-first UI.
- Stores job results and cache locally in SQLite.

## Project Structure
- `backend/server.py` HTTP server and API routes
- `backend/bluesky_client.py` BlueSky public API client
- `backend/analyzer.py` deterministic summarization logic
- `backend/storage.py` SQLite persistence for jobs/cache
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

## API Endpoints (Phase 1)
- `GET /api/health`
- `POST /api/analyze`
  - body: `{ "handle": "alice.bsky.social", "max_items": 200, "use_cache": true }`
- `GET /api/jobs/{job_id}`
- `GET /api/summary/{job_id}`
- `GET /api/user/raw?handle=alice.bsky.social`

See `docs/api.md` for details.

## Tests
```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Data and Privacy
- Uses public BlueSky data only.
- No private account access.
- Caches fetched public data and summaries in local SQLite at `data/app.db`.

## Roadmap
- Phase 1: MVP ingestion + deterministic summary + mobile UI
- Phase 2: evidence-linked narrative summaries and confidence labels
- Phase 3: time comparison, export, and observability

Detailed task breakdown: `docs/task-breakdown.md`
