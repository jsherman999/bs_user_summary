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
  "use_cache": true,
  "cache_age_seconds": 900
}
```

Notes:
- `handle` required.
- `max_items` clamped to `25..500`.
- `cache_age_seconds` clamped to `60..86400`.

Response:
```json
{
  "job_id": 1,
  "status": "queued",
  "handle": "alice.bsky.social"
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

Phase 2 response sections:
- `generated_at`
- `user`
- `metrics`
- `top_terms`
- `top_topics`
- `takes`
- `claims`
- `evidence`
- `uncertainty_notes`
- `honesty_notes`
- `summary_text`

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

## `GET /api/user/raw?handle={handle}`
Returns latest cached raw BlueSky response normalization for a handle.
