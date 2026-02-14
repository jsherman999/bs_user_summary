# API Reference

Base URL when running locally: `http://127.0.0.1:8080`

## `GET /api/health`
Returns service health.

Response:
```json
{ "ok": true, "service": "bs-user-summary" }
```

## `POST /api/analyze`
Start an async analysis job.

Request body:
```json
{
  "handle": "alice.bsky.social",
  "max_items": 200,
  "comparison_window_days": 30,
  "use_cache": true,
  "cache_age_seconds": 900,
  "enable_llm": true,
  "llm_provider": "auto",
  "llm_model": "",
  "llm_max_posts": 500
}
```

Notes:
- `handle` required.
- `max_items` clamped to `25..500`.
- `comparison_window_days` clamped to `7..90`.
- `cache_age_seconds` clamped to `60..86400`.
- `llm_provider` supported values: `auto`, `openai`, `openrouter`, `none`.
- `llm_max_posts` clamped to `25..500`.

Response:
```json
{
  "job_id": 1,
  "status": "queued",
  "handle": "alice.bsky.social",
  "comparison_window_days": 30,
  "llm_enabled": true,
  "llm_provider": "auto",
  "llm_model": null
}
```

## `GET /api/jobs/{job_id}`
Read current job status.

Response:
```json
{
  "id": 1,
  "handle": "alice.bsky.social",
  "status": "running",
  "created_at": 1739550000,
  "updated_at": 1739550001,
  "error": null
}
```

## `GET /api/summary/{job_id}`
Read summary for completed job.

Phase 3 response sections:
- `generated_at`
- `comparison_window_days`
- `user`
- `metrics`
- `top_terms`
- `top_topics`
- `takes`
- `claims`
- `llm_assessment`
- `evidence`
- `comparison`
- `uncertainty_notes`
- `honesty_notes`
- `summary_text`

Heuristic notes:
- `top_terms` excludes common platform/URL/identity noise tokens.
- `takes` include stance statements only when topic mention volume is sufficient (currently 5+ sampled items).
- low-volume topic signals are reported under `uncertainty_notes`.
- `llm_assessment` falls back to deterministic output if provider is unavailable.

Example claim object:
```json
{
  "id": "claim-replies",
  "type": "interaction",
  "text": "Replies are 40.0% of sampled activity.",
  "confidence": 0.9,
  "evidence_ids": ["ev1", "ev7"]
}
```

Example evidence object:
```json
{
  "id": "ev1",
  "uri": "at://did:.../app.bsky.feed.post/abc123",
  "created_at": "2026-02-13T10:00:00+00:00",
  "text": "post text",
  "is_reply": false,
  "topics": ["technology"]
}
```

Example LLM assessment object:
```json
{
  "enabled": true,
  "source": "llm",
  "provider": "openai",
  "model": "gpt-5-mini",
  "status": "ok",
  "topic_alignments": [
    {
      "topic": "technology",
      "alignment": "mixed",
      "confidence": 0.68,
      "mention_count": 28,
      "evidence_ids": ["ev5", "ev12", "ev33"]
    }
  ],
  "usage": { "input_tokens": 34120, "output_tokens": 5220, "total_tokens": 39340 }
}
```

Example comparison object:
```json
{
  "window_days": 30,
  "recent_window": { "items": 25, "replies": 10, "reply_ratio": 0.4 },
  "prior_window": { "items": 12, "replies": 3, "reply_ratio": 0.25 },
  "delta": { "items": 13, "replies": 7, "reply_ratio": 0.15, "activity_direction": "higher" }
}
```

## `GET /api/export/{job_id}.json`
Returns the same payload as `GET /api/summary/{job_id}`.

## `GET /api/export/{job_id}.md`
Returns a Markdown report built from summary metrics, claims, takes, comparison, and uncertainty notes.

## `GET /api/stats`
Service observability endpoint.

Response includes:
- `uptime_seconds`
- `started_at`
- `job_counts`
- `cache_entries`
- `request_counts`

## `POST /api/maintenance/cleanup`
Delete old cache and completed/failed jobs.

Request body:
```json
{ "max_age_days": 30 }
```

Response:
```json
{
  "max_age_days": 30,
  "jobs_deleted": 4,
  "cache_deleted": 1,
  "cutoff_epoch": 1736900000
}
```

## `GET /api/user/raw?handle={handle}`
Returns latest cached raw BlueSky response normalization for a handle.
