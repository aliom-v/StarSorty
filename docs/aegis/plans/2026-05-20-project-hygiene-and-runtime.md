# Project Hygiene and Runtime Plan

Date: 2026-05-20

## Goal

Reduce local-environment drift and accidental workspace clutter while preserving the existing single-machine StarSorty development flow. The work covers:

1. Make the repository root `.venv` the documented and scripted Python environment for local host startup.
2. Add safe cross-platform cleanup and data-reset commands so generated files are removed intentionally, not manually.
3. Strengthen manual override tag consistency checks so unknown taxonomy tags cannot silently become empty overrides.
4. Keep existing CI coverage intact by adding tests under commands CI already runs.

## Architecture

Current local development has these owners:

1. `package.json` is the root command surface.
2. `scripts/run-platform.js` dispatches `npm run start|dev|stop|status` to platform scripts.
3. `scripts/unix/start.sh` and `scripts/windows/start.ps1` start API and Web on host ports `4321` and `1234`.
4. `scripts/run-api-tests.js` and `scripts/lib/python-runner.js` own API test environment probing and Docker fallback.
5. `scripts/run-web-command.js` owns web dependency preflight.
6. `api/app/routes/repos.py` owns override request normalization before calling `api/app/db/override.py`.
7. `api/app/db/schema.py` owns `repo_effective_tags` lookup table behavior through SQLite triggers.
8. `.github/workflows/ci.yml` already runs docs, script tests, API tests, and web tests/build/smoke.

The new cleanup command should be a Node script so it is cross-platform like the rest of the root script surface. Platform startup scripts remain platform-native because they launch background processes differently.

## Tech Stack

- Root scripts: Node.js CommonJS, `node:test`, `npm`.
- Unix startup: Bash.
- Windows startup: PowerShell.
- Backend: FastAPI, Pydantic, aiosqlite, pytest.
- Frontend: Next.js, npm.
- Storage: SQLite under `data/app.db` for host development.
- CI: GitHub Actions, Node 20, Python 3.11.

## Baseline/Authority Refs

- `README.md`
- `CONTRIBUTING.md`
- `scripts/README.md`
- `docs/guides/configuration.md`
- `docs/guides/project-structure.md`
- `docs/roadmap/optimization-execution-plan.md`
- `docs/aegis/baseline/2026-05-20-initial-baseline.md`
- `scripts/unix/start.sh`
- `scripts/windows/start.ps1`
- `scripts/windows/dev.ps1`
- `package.json`
- `.github/workflows/ci.yml`
- `api/app/routes/repos.py`
- `api/app/db/override.py`
- `api/app/db/schema.py`
- `api/tests/test_phase1_optimizations.py`
- `tests-node/*.test.js`

## Compatibility Boundary

- Keep root npm commands as the recommended entry point.
- Keep `npm run start`, `npm run dev`, `npm run stop`, and `npm run status` names stable.
- Keep `npm run api:test`, `npm run web:test`, `npm run web:lint`, `npm run web:build`, and `npm run web:smoke` names stable.
- Do not delete `.env`, root `.venv`, or `data/app.db` in the default cleanup command.
- `npm run reset:data` may remove `data/app.db`, but only when explicitly requested.
- `npm run clean:deps` may remove `web/node_modules` and the legacy API subdirectory virtual environment, but must preserve root `.venv`.
- Local host startup uses root `.venv`; the legacy API subdirectory virtual environment is retired from scripts and docs.
- `PATCH /repos/{full_name}/override` continues accepting `tags` and `tag_ids`, but unknown taxonomy inputs should return `400` instead of being silently dropped.

## Verification

Run targeted RED/GREEN commands as each task changes:

```bash
cd /home/aliom/project/StarSorty
npm run scripts:test
./.venv/bin/python -m pytest -o cache_dir=/tmp/starsorty_pytest_cache api/tests/test_phase1_optimizations.py api/tests/test_phase2_route_smoke.py
npm run docs:check
```

Before commit/push, run:

```bash
cd /home/aliom/project/StarSorty
npm run scripts:test
./.venv/bin/python -m pytest -o cache_dir=/tmp/starsorty_pytest_cache api/tests/test_phase1_optimizations.py api/tests/test_phase2_route_smoke.py api/tests/test_user_manual_override_preference.py
npm run docs:check
git status -sb
```

## Task 1: Make Root `.venv` the Local Host Runtime

Files:

- Modify `scripts/unix/start.sh`.
- Modify `scripts/windows/start.ps1`.
- Modify `scripts/windows/dev.ps1`.
- Modify `CONTRIBUTING.md`.
- Modify `scripts/README.md`.
- Create `tests-node/runtime-scripts.test.js`.

Why:

The project currently documents root `.venv` for manual development but host startup scripts still pointed at the old API subdirectory environment. That created duplicated Python environments and confusing cleanup decisions.

Impact/Compatibility:

The stable commands stay unchanged. Users run `python -m venv .venv` from the repository root and install `api/requirements-dev.txt` there. The legacy API subdirectory environment becomes obsolete local debris and can be removed with `npm run clean:deps`.

Repair Track:

- Root cause: startup scripts and contribution docs disagree on the Python venv location.
- Canonical owner: root script surface plus platform startup scripts.
- Minimal change: update startup scripts to use root `.venv`, then update docs and script tests.
- Verification: `npm run scripts:test` plus docs check.

Retirement Track:

- Retired object: the old API subdirectory virtual environment as the startup runtime.
- Retained boundary: existing users can recreate root `.venv` from documented commands.
- Future trigger: remove any remaining legacy API venv references if new docs/scripts reintroduce them.

Steps:

1. Write `tests-node/runtime-scripts.test.js` asserting Unix and Windows startup scripts reference root `.venv` and do not reference the legacy API venv.
2. Run `npm run scripts:test`; expected RED is a failure showing the old API venv still appears in startup scripts.
3. Update Unix and Windows startup scripts to use root `.venv` paths and root-venv setup messages.
4. Update `CONTRIBUTING.md` and `scripts/README.md` so local startup and manual backend startup use the same root `.venv` commands.
5. Re-run `npm run scripts:test` and `npm run docs:check`; expected GREEN is all script tests and docs checks passing.

## Task 2: Add Safe Cleanup and Explicit Data Reset Commands

Files:

- Create `scripts/lib/clean-workspace.js`.
- Create `scripts/clean-workspace.js`.
- Create `tests-node/clean-workspace.test.js`.
- Modify `package.json`.
- Modify `scripts/README.md`.
- Modify `README.md` if the root command list needs a short cleanup entry.

Why:

Generated files were previously cleaned by hand. That makes it easy to delete too much or leave stale generated artifacts behind.

Impact/Compatibility:

Default cleanup removes only safe generated files and Python caches outside `.venv`. Dependency and data cleanup require explicit flags through dedicated npm scripts.

Repair Track:

- Root cause: no first-class cleanup contract.
- Canonical owner: root npm scripts backed by a testable Node helper.
- Minimal change: add cleanup helper, CLI wrapper, npm scripts, docs, and script tests.
- Verification: `npm run scripts:test` and a dry-run smoke command.

Retirement Track:

- Retired object: manual ad hoc cleanup commands.
- Retained boundary: `.env`, root `.venv`, and `data/app.db` are preserved by default.
- Future trigger: add more generated paths only with tests proving default cleanup safety.

Steps:

1. Write tests that create a temporary StarSorty-like tree and assert:
   - default cleanup removes `.cache`, `.pytest_cache`, `.run`, `logs`, the Next.js build output under `web`, `web/out`, and source `__pycache__`;
   - default cleanup preserves `.env`, root `.venv`, `data/app.db`, and `web/node_modules`;
   - dependency cleanup removes `web/node_modules` and the legacy API subdirectory virtual environment but preserves root `.venv`;
   - data reset removes `data/app.db` only when requested.
2. Run `npm run scripts:test`; expected RED is module-not-found for `scripts/lib/clean-workspace.js`.
3. Implement the cleanup helper and CLI wrapper with `--dry-run`, `--deps`, and `--data`.
4. Add npm scripts:
   - `clean`
   - `clean:dry-run`
   - `clean:deps`
   - `reset:data`
   - `clean:all`
5. Update `scripts/README.md` and the root README command list with concise cleanup/reset guidance.
6. Re-run `npm run scripts:test`, `node scripts/clean-workspace.js --dry-run`, and `npm run docs:check`; expected GREEN is tests passing and dry-run listing only intended paths.

## Task 3: Tighten Override Tag Consistency at the API Boundary

Files:

- Modify `api/app/routes/repos.py`.
- Modify `api/tests/test_phase2_route_smoke.py`.
- Modify `api/tests/test_phase1_optimizations.py` or add a focused API/DB test file if the existing fixture becomes too large.

Why:

Manual override tags and tag IDs feed `repo_effective_tags`, search filters, override history, and training samples. Unknown taxonomy inputs should be rejected before persistence instead of being converted to empty overrides.

Impact/Compatibility:

Known tag labels and tag IDs keep working. Unknown tag labels or IDs return `400` with a clear message. This makes invalid manual override requests visible instead of silently discarding user input.

Repair Track:

- Root cause: taxonomy normalization returned unknown values but route normalization ignored them.
- Canonical owner: `api/app/routes/repos.py` because request normalization happens before persistence.
- Minimal change: raise `HTTPException(400)` when nonblank override tag inputs cannot be normalized.
- Verification: focused route tests and SQLite lookup integration tests.

Retirement Track:

- Retired object: silent dropping of unknown manual override tags.
- Retained boundary: DB layer remains a persistence owner and does not need taxonomy knowledge.
- Future trigger: if free-form manual tags become a product requirement, add a dedicated schema for unmatched display tags rather than overloading `tag_ids`.

Steps:

1. Write tests proving:
   - unknown `tag_ids` in `OverrideRequest` raise `HTTPException(400)`;
   - unknown `tags` in `OverrideRequest` raise `HTTPException(400)`;
   - valid `tag_ids`, valid `tags`, both fields, and explicit clearing keep `repo_effective_tags`, search lookup, override history, and training samples consistent.
2. Run:

   ```bash
   ./.venv/bin/python -m pytest -o cache_dir=/tmp/starsorty_pytest_cache api/tests/test_phase2_route_smoke.py api/tests/test_phase1_optimizations.py
   ```

   Expected RED is unknown-tag tests failing because current route normalization ignores unknown values.
3. Implement the route normalization check using the existing `normalize_tag_ids` unknown return value.
4. Re-run the same pytest command; expected GREEN is all targeted API tests passing.

## Task 4: CI and Documentation Closure

Files:

- Modify `.github/workflows/ci.yml` only if new tests are outside existing CI commands.
- Modify `docs/aegis/INDEX.md`.
- Modify `docs/aegis/README.md`.
- Modify this plan if implementation evidence changes scope.

Why:

The project should keep the same CI entry points while making the new guarantees obvious in project docs.

Impact/Compatibility:

No CI command names change. If tests remain under `tests-node` and `api/tests`, current CI jobs already enforce them.

Repair Track:

- Root cause: optimization guidance was spread across docs and conversation, not captured as an executable plan.
- Canonical owner: `docs/aegis/plans/2026-05-20-project-hygiene-and-runtime.md`.
- Minimal change: index the plan and update active-plan notes.
- Verification: `npm run docs:check`.

Retirement Track:

- Retired object: duplicated manual cleanup advice.
- Retained boundary: root README stays concise and links to `scripts/README.md`.
- Future trigger: if command behavior changes again, update `scripts/README.md` first and keep README short.

Steps:

1. Update Aegis index and README to reference this plan.
2. Confirm `.github/workflows/ci.yml` already runs `npm run scripts:test` and `python -m pytest -q api/tests`; update comments or job names only if helpful.
3. Run `npm run docs:check`.
4. Run final targeted verification listed above.
5. Commit and push:

   ```bash
   git add package.json scripts tests-node api/app/routes/repos.py api/tests README.md CONTRIBUTING.md docs .github/workflows/ci.yml
   git commit -m "Add workspace hygiene tooling"
   git push origin main
   git fetch --prune origin
   git status -sb
   ```

## Risks and Rollback

- Root `.venv` startup can surprise users who already created the legacy API subdirectory environment; rollback is restoring the old script path, but the preferred fix is to recreate root `.venv`.
- `reset:data` intentionally removes local SQLite state; it must stay opt-in and documented as destructive.
- Unknown tag rejection changes invalid requests from silent no-op-like behavior to `400`; rollback is removing the unknown check, but that reintroduces hidden data loss.
- Full `api/tests` can be slow or hang in this environment; final verification should report exact commands run and any command that could not complete.
