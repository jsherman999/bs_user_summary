# BlueSky User Summary App Task Breakdown

## Assumptions
- Target host: macOS laptop/desktop on a trusted local network.
- Target client: mobile browser on same LAN.
- Data source: public BlueSky XRPC endpoints only.
- Runtime: Python 3.11+ (standard library only, no external package install required).

## Build Plan With Estimates

1. **Phase 1: MVP ingestion + deterministic summary + mobile UI** (8-12 hours)
- Backend HTTP server and local API routes.
- BlueSky public fetch pipeline (handle resolution, profile, paginated feed fetch).
- SQLite caching of raw fetched records and completed job summaries.
- Deterministic analytics (activity, reply ratio, top terms/topics, timeline window).
- Mobile-first frontend (single-page flow: handle input -> progress -> summary).
- LAN run support (`--host 0.0.0.0`) and basic run scripts.
- Documentation baseline (`README`, API docs, local run steps).

2. **Phase 2: Evidence-linked narrative summaries + stronger transparency** (6-10 hours)
- Add claim-to-evidence mapping for summary statements.
- Add topic/take extraction with confidence labeling.
- Add explicit uncertainty markers when data is sparse or mixed.
- UI evidence drill-down and "claim support" panel.
- Add tests for claim grounding and analyzer behavior.
- Update docs and changelog.

3. **Phase 3: Time comparison, export, and observability** (6-9 hours)
- Add optional comparison windows (recent vs prior period).
- Add JSON/Markdown export endpoints for reports.
- Add lightweight observability (request/job logs and stats endpoint).
- Add retention controls and cleanup utilities for cached analyses.
- Final documentation pass to ensure all endpoints/features are reflected.
- Update docs and changelog.

## Definition of Done
- Every major summary claim references concrete evidence from fetched public posts/replies.
- App runs on macOS and is reachable from local LAN clients.
- README and docs match implemented endpoints, configuration, and known limits.
- Changelog updated phase-by-phase with user-visible changes.
