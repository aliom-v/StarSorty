# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Documentation
- Consolidated doc entry paths around `docs/README.md` and reduced repeated navigation content in guide pages.
- Clarified the difference between stack bring-up, admin write access, GitHub sync prerequisites, and AI classification prerequisites across the main deployment docs.
- Added more explicit deployment verification, same-site `/api` proxy, admin session, and local-development fallback guidance to match the current runtime behavior.
- Documented that unauthenticated local sync can still work with explicit usernames, but README fetching during classification is more likely to hit GitHub anonymous rate limits unless `GITHUB_TOKEN` is configured or `include_readme` is disabled.

### Fixed
- Restored the built-in taxonomy fallback when `AI_TAXONOMY_PATH` is present in `.env` but left blank.
- Made `/classify/stop` actively cancel the in-flight background task so a rate-limited README fetch no longer leaves classification stuck in a long sleep.

## [0.2.0] - 2026-03-07

### Added
- Added API regression coverage for release-readiness permissions, route smoke paths, stats snapshots, consistency checks, and Phase 1 optimizations.
- Added frontend server smoke checks for the home page, admin page, and settings page.
- Added CI gating for API tests, web lint/build, and web smoke validation.
- Added performance benchmark entrypoint for search and large-account sync scenarios.
- Added consistency inspection endpoint `/metrics/consistency` and stats snapshot reuse coverage.

### Changed
- Tightened admin access boundaries for `GET /settings`, `GET /preferences/{user_id}`, `GET /interest/{user_id}`, and `GET /repos/failed`.
- Split public client config reads to `GET /api/config/client-settings` and updated the settings page to use only public-safe fields.
- Optimized relevance reranking, sync star-user lookup batching, and taxonomy/rules hot-cache behavior.
- Reused versioned stats snapshots to avoid unnecessary full aggregation when repo data has not changed.
- Updated project documentation structure and release-readiness guidance to match the current implementation.

### Security
- Enforced production startup failure when `APP_ENV=production` and `ADMIN_TOKEN` is missing.
- Restricted production CORS configuration to explicit origins and exposed security self-check data only to authenticated admin health requests.
- Protected export endpoints and other management surfaces with admin authentication.

### Notes
- This release focuses on moving the project from internal-use readiness toward a more stable multi-user self-hosted delivery baseline.
