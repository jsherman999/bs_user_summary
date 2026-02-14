# Changelog

## [Unreleased]

## [0.3.1] - 2026-02-14
### Added
- macOS `launchd` service automation with `install/start/stop/restart/status/logs/uninstall` commands.
- launchd documentation for boot-time LAN hosting setup.

### Changed
- launchd install now auto-selects shell `python3` and validates Python 3.11+ before service registration.
- Tuned analyzer heuristics using real-handle end-to-end output:
  - top-term filtering now removes URL/mention/platform/identity noise.
  - topic takes now require higher signal volume before stance claims.
  - low-signal topics move to uncertainty notes instead of stance claims.

## [0.3.0] - 2026-02-14
### Added
- Comparison-window analysis in summary output (recent vs prior period deltas).
- Export endpoints for JSON and Markdown reports.
- Observability endpoint (`/api/stats`) with uptime, job counts, cache count, and request counters.
- Retention cleanup endpoint (`/api/maintenance/cleanup`) for old cache and completed/failed jobs.
- UI support for comparison window input and export links.
- Analyzer/storage test coverage for comparison and cleanup behavior.

## [0.2.0] - 2026-02-14
### Added
- Claim-level evidence linking in summary output.
- Topic take extraction with confidence values and uncertainty notes.
- Honesty notes that describe data boundaries.
- Mobile UI sections for claims, takes, uncertainty, and evidence items.
- Analyzer tests to enforce claim grounding to evidence IDs.

## [0.1.0] - 2026-02-14
### Added
- Initial project scaffold with Python backend and mobile-friendly frontend.
- BlueSky public API integration for handle resolution, profile fetch, and paginated feed fetch.
- Async analysis jobs with SQLite-backed storage and short-term cache.
- Deterministic summary metrics (activity, reply ratio, top terms/topics).
- Phase 1 API endpoints and browser UI flow.
- Initial documentation (`README`, API docs, task breakdown).
- Unit tests for analyzer and storage.
