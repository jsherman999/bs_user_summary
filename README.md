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
- Optional LLM alignment layer (OpenAI/OpenRouter) with deterministic fallback:
  - per-topic likely alignment (`for`, `against`, `mixed`, `unclear`)
  - usage accounting (`input_tokens`, `output_tokens`)
  - automatic fallback when provider/key/model is unavailable
  - stronger political-topic cue detection in prompt + conservative uncertainty when unclear
- Live progress reporting during jobs:
  - fetch stage details
  - LLM chunk stage details
  - `x/y` counters for posts/chunks analyzed
  - transient poll retry handling for temporary DB/network failures
  - persisted job recovery (auto-resume on reload if a run is still in progress)
- Adds time-window comparison (recent window vs prior window).
- Supports summary export in JSON and Markdown formats.
- Exposes observability stats and retention cleanup endpoints.
- Presents all results in a mobile-first UI, including evidence and comparison panels.
- Stores job results and cache locally in SQLite.
- Uses SQLite WAL + busy-timeout + retry/backoff to improve stability during long-running scans.
- Uses in-memory runtime fallbacks for active job status/summary responses if SQLite has a transient open failure.

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

## Auto-Start On macOS (launchd)
Install and start a background service that binds to LAN:

```bash
./launchd/control.sh install
```

Common service commands:

```bash
./launchd/control.sh status
./launchd/control.sh logs
./launchd/control.sh restart
./launchd/control.sh uninstall
```

Optional environment overrides before install:
- `BS_APP_HOST` (default `0.0.0.0`)
- `BS_APP_PORT` (default `8080`)
- `PYTHON_BIN` (default: current `python3` in your shell `PATH`, must be Python 3.11+)

Details: `docs/launchd.md`

## API Endpoints (Phase 3)
- `GET /api/health`
- `POST /api/analyze`
  - body: `{ "handle": "alice.bsky.social", "max_items": 200, "comparison_window_days": 30, "use_cache": true }`
- `GET /api/jobs/{job_id}`
- `GET /api/summary/{job_id}`
- `GET /api/export/{job_id}.json`
- `GET /api/export/{job_id}.md`
- `GET /api/stats`
- `GET /api/llm/models?provider=openai|openrouter|auto&free_only=true|false`
- `POST /api/maintenance/cleanup`
- `GET /api/user/raw?handle=alice.bsky.social`

See `docs/api.md` for full payload examples.

## LLM Configuration
Request-level options on `POST /api/analyze`:
- `enable_llm` boolean (default `true`)
- `llm_provider` one of `auto`, `openai`, `openrouter`, `none`
- `llm_model` optional explicit model name
- `llm_max_posts` integer `25..500` (default `500`)

Environment options:
- `BS_LLM_ENABLED=true|false`
- `BS_LLM_PROVIDER=auto|openai|openrouter|none`
- `BS_LLM_MODEL=<model-name>`
- `BS_LLM_MAX_POSTS=500`
- `OPENAI_API_KEY=<key>` for `openai`
- `OPENROUTER_API_KEY=<key>` for `openrouter`

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
