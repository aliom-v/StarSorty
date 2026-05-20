# Doctor and Safety Closure Plan

Date: 2026-05-20

## Goal

Add a single read-only `npm run doctor` command for local environment checks, make `reset:data` safer with an explicit dry-run companion, keep cleanup safety covered by CI-facing tests, lock the override reject path with mixed known/unknown inputs, and finish the documentation boundary cleanup so the scripts surface has one authority.

This work keeps the current StarSorty single-machine development flow intact. It does not change the app runtime model, the SQLite schema, or the existing `npm run start|dev|stop|status` entry points.

## Architecture

Current owners:

1. `package.json` is the root command surface.
2. `scripts/lib/clean-workspace.js` and `scripts/clean-workspace.js` own safe cleanup and explicit data removal.
3. `scripts/lib/python-runner.js` is the closest existing pattern for environment probing.
4. `scripts/unix/status.sh` and `scripts/windows/status.ps1` already own port-listening checks.
5. `api/app/routes/repos.py` owns override request normalization before persistence.
6. `tests-node/*.test.js` and `api/tests/*.py` own the regression layer.
7. `scripts/README.md` is the authoritative scripts document; `README.md` and `CONTRIBUTING.md` are thin entry points.
8. `.github/workflows/ci.yml` already runs `npm run scripts:test` and `npm run docs:check`, so no workflow change is expected.

The new `doctor` command should be a small Node helper plus CLI wrapper, matching the existing `clean-workspace` pattern: pure report-building logic in `scripts/lib/`, thin command entry point in `scripts/`, and coverage in `tests-node/`.

## Tech Stack

- Root scripts: Node.js CommonJS, `node:test`, `npm`.
- Unix startup and status: Bash.
- Windows startup and status: PowerShell.
- Backend: FastAPI, Pydantic, aiosqlite, pytest.
- Frontend: Next.js, npm.
- Storage: SQLite under `data/app.db` for host development.
- CI: GitHub Actions, Node 20, Python 3.11.

## Baseline/Authority Refs

- `README.md`
- `CONTRIBUTING.md`
- `scripts/README.md`
- `scripts/lib/clean-workspace.js`
- `scripts/lib/python-runner.js`
- `scripts/unix/status.sh`
- `scripts/windows/status.ps1`
- `api/app/routes/repos.py`
- `api/tests/test_phase2_route_smoke.py`
- `tests-node/clean-workspace.test.js`
- `tests-node/runtime-scripts.test.js`
- `docs/aegis/plans/2026-05-20-project-hygiene-and-runtime.md`
- `docs/aegis/baseline/2026-05-20-initial-baseline.md`

## Compatibility Boundary

- Keep `npm run start`, `npm run dev`, `npm run stop`, and `npm run status` names stable.
- Keep `npm run clean`, `npm run clean:dry-run`, `npm run clean:deps`, and `npm run clean:all` behavior stable.
- Additive command names are allowed for `npm run doctor` and `npm run reset:data:dry-run`.
- `npm run reset:data` stays explicit and destructive, and continues to target only `data/app.db`.
- `doctor` is read-only with respect to application files and data. It may refresh `origin/main` before comparing it with local `HEAD`, but it must not edit source files, delete data, or start services.
- `doctor` exits non-zero on hard failures only: missing root `.venv`, missing `web/node_modules`, any `origin/main` divergence or fetch failure, or API port 4321 conflict. `data/app.db` absence is reported but not treated as fatal.
- `PATCH /repos/{full_name}/override` keeps the current fail-fast behavior for unknown tag values, including mixed known/unknown payloads.
- `README.md` and `CONTRIBUTING.md` stay thin entry points; `scripts/README.md` remains the single authority for command details.

## Verification

Run these commands as the slices land:

```bash
cd /home/aliom/project/StarSorty
npm run scripts:test
npm run docs:check
npm run doctor
npm run clean:dry-run
npm run reset:data:dry-run
./.venv/bin/python -m pytest -o cache_dir=/tmp/starsorty_pytest_cache api/tests/test_phase2_route_smoke.py::test_repos_override_rejects_unknown_tag_inputs
```

Before commit and push, run:

```bash
cd /home/aliom/project/StarSorty
npm run scripts:test
npm run docs:check
npm run doctor
git status -sb
```

## Task 1: Add a Read-Only `doctor` Command

Files:

- Create `scripts/lib/doctor.js`.
- Create `scripts/doctor.js`.
- Modify `package.json`.
- Create `tests-node/doctor.test.js`.
- Modify `scripts/README.md`.
- Modify `README.md`.
- Modify `CONTRIBUTING.md`.

Why:

The current workflow requires a mix of shell commands, `git` checks, and port probes to answer a simple question: is the local environment ready or is it drifting? A single command lowers that manual overhead and makes the answer repeatable.

Impact/Compatibility:

The command is additive and read-only. It should report the state of the root `.venv`, `web/node_modules`, `data/app.db`, `origin/main`, and API port 4321 without mutating application state. It may refresh `origin/main` before comparison so the sync check reflects the current remote, not a stale local ref.

Repair Track:

- Root cause: environment readiness is currently spread across several commands and status files.
- Canonical owner: a new root `doctor` command backed by `scripts/lib/doctor.js`.
- Minimal change: report the five checks in one place, keep the command non-interactive, and surface hard failures with a non-zero exit code.
- Verification: `npm run scripts:test` and `npm run doctor`.

Retirement Track:

- Retired object: ad hoc manual check chains for venv / dependency / port / remote status.
- Retained boundary: `npm run status` still exists for simple port status; `doctor` is the stronger readiness gate.
- Future trigger: if the local environment acquires a new required runtime dependency, add it to the doctor report with a test first.

Steps:

1. Write `tests-node/doctor.test.js` to pin the exit-code matrix and report formatting for healthy, missing-dependency, port-conflict, and origin-divergence cases.
2. Run `npm run scripts:test`; expected RED is the missing doctor implementation or a failing hard-failure matrix.
3. Implement `scripts/lib/doctor.js`, `scripts/doctor.js`, and the `doctor` script entry in `package.json`.
4. Re-run `npm run scripts:test` and `npm run doctor`; expected GREEN is a stable report with exit 0 only when the hard-failure set is clear.
5. Update `scripts/README.md`, `README.md`, and `CONTRIBUTING.md` so the new command is documented once and the other docs just link to it.

## Task 2: Add a Safer `reset:data` Preview Path

Files:

- Modify `package.json`.
- Modify `tests-node/clean-workspace.test.js`.
- Modify `scripts/README.md`.

Why:

`reset:data` is intentionally destructive, but the current surface gives users no preview path. A dry-run alias makes the target explicit before any local database deletion happens.

Impact/Compatibility:

`reset:data` stays destructive and still removes only `data/app.db`. The new dry-run alias must print the same target without deleting anything.

Repair Track:

- Root cause: an explicit destructive command exists without a built-in preview path.
- Canonical owner: root npm scripts plus the existing cleanup helper.
- Minimal change: add a dry-run alias, keep the destructive command unchanged, and document the preview path next to the command.
- Verification: `npm run reset:data:dry-run` and `npm run scripts:test`.

Retirement Track:

- Retired object: undocumented ad hoc previews for database deletion.
- Retained boundary: the destructive command remains available for deliberate reset workflows.
- Future trigger: if `reset:data` ever needs to remove more than `data/app.db`, that change must go through a separate plan and tests.

Steps:

1. Extend `tests-node/clean-workspace.test.js` with a case that asserts the dry-run path targets `data/app.db` and does not delete the file.
2. Run `npm run scripts:test`; expected RED is the missing preview alias or a mismatch in the data-reset target.
3. Add `reset:data:dry-run` to `package.json`, reusing the existing cleanup helper with `--data --dry-run`.
4. Re-run `npm run reset:data:dry-run` and `npm run scripts:test`; expected GREEN is a preview-only report and no file deletion.
5. Document the new preview path in `scripts/README.md`.

## Task 3: Keep Cleanup Dry-Run Coverage in CI

Files:

- Modify `tests-node/clean-workspace.test.js`.
- Modify `scripts/README.md` if the dry-run output needs a tighter command note.

Why:

The cleanup command already exists, but the safe default needs a small regression net so the dry-run surface keeps proving that `.env`, root `.venv`, `data/app.db`, and `web/node_modules` stay untouched unless explicitly requested.

Impact/Compatibility:

No workflow changes are expected. The existing `npm run scripts:test` entry already runs in CI, so stronger Node tests are enough to keep the cleanup boundary protected.

Repair Track:

- Root cause: safe cleanup is currently proven by helper tests, but the dry-run command deserves an explicit regression in the same suite.
- Canonical owner: `tests-node/clean-workspace.test.js` plus the existing cleanup helper.
- Minimal change: add or tighten the dry-run assertions so they cover both the safe default tree and the explicit dependency / data flags.
- Verification: `npm run scripts:test` and `npm run clean:dry-run`.

Retirement Track:

- Retired object: manual visual inspection of cleanup targets.
- Retained boundary: the default cleanup must never delete `.env`, root `.venv`, `data/app.db`, or `web/node_modules`.
- Future trigger: any new generated path should be added only with a matching test.

Steps:

1. Add or tighten the temp-tree assertions in `tests-node/clean-workspace.test.js` so the default cleanup and dry-run surface are both covered.
2. Run `npm run scripts:test`; expected RED is a regression in the dry-run target list or a changed default boundary.
3. Adjust the cleanup helper only if the current dry-run output is too weak to prove the safe boundary.
4. Re-run `npm run clean:dry-run` and `npm run scripts:test`; expected GREEN is a stable dry-run summary and preserved runtime inputs.
5. Keep `.github/workflows/ci.yml` unchanged unless a new command falls outside `npm run scripts:test`.

## Task 4: Lock the Override Reject Path Against Mixed Unknown Tags

Files:

- Modify `api/tests/test_phase2_route_smoke.py`.

Why:

The API boundary already rejects unknown override tags, but the mixed-input case is the easiest place for a future regression to sneak back in and silently accept partial garbage.

Impact/Compatibility:

Known tags stay valid. Any payload containing at least one unknown tag value must still fail with `400` before persistence, including mixed known/unknown `tags` and `tag_ids` payloads.

Repair Track:

- Root cause: mixed known/unknown payloads are easy to mishandle when only the all-unknown case is tested.
- Canonical owner: `api/app/routes/repos.py`, guarded by route tests.
- Minimal change: add route-level regression coverage for mixed known/unknown input and keep the route fail-fast behavior unchanged.
- Verification: the targeted pytest command below.

Retirement Track:

- Retired object: any future attempt to silently drop unknown tag values at the route boundary.
- Retained boundary: `update_override` remains a persistence owner, not a taxonomy parser.
- Future trigger: if free-form unmatched tags become a product requirement, that must be a separate schema design.

Steps:

1. Extend `test_repos_override_rejects_unknown_tag_inputs` with mixed known/unknown `tag_ids` and `tags` payloads.
2. Run:

   ```bash
   ./.venv/bin/python -m pytest -o cache_dir=/tmp/starsorty_pytest_cache api/tests/test_phase2_route_smoke.py::test_repos_override_rejects_unknown_tag_inputs
   ```

   Expected RED is any case where the route accepts partial unknown input.
3. Keep the route behavior fail-fast; do not let the test pass by weakening the validation contract.
4. Re-run the same pytest command; expected GREEN is a 400 for every mixed unknown case.
5. Leave the database layer unchanged unless the route contract exposes a real persistence bug.

## Task 5: Tighten Documentation Boundaries and Aegis Metadata

Files:

- Modify `README.md`.
- Modify `CONTRIBUTING.md`.
- Modify `scripts/README.md`.
- Modify `docs/aegis/README.md`.
- Modify `docs/aegis/INDEX.md`.

Why:

The scripts surface is now broader. The docs need to make one file authoritative for command details, while the root README and contribution guide stay as entry points instead of duplicating usage notes.

Impact/Compatibility:

The root README and contribution guide should only point readers at `scripts/README.md` for the detailed command surface. The Aegis index should reflect this plan as the active follow-up to the previous hygiene/runtime work.

Repair Track:

- Root cause: command details are spread across multiple docs, which makes future drift more likely.
- Canonical owner: `scripts/README.md` for command details; `README.md` and `CONTRIBUTING.md` for short pointers only.
- Minimal change: remove duplicated command prose, add direct links, and update the Aegis active plan pointer.
- Verification: `npm run docs:check`.

Retirement Track:

- Retired object: repeated command explanations in root docs.
- Retained boundary: `README.md` still gives a quick path into the project, and `CONTRIBUTING.md` still explains how to work locally.
- Future trigger: if another script command is added, it should be documented once in `scripts/README.md` and linked elsewhere.

Steps:

1. Trim the duplicated command prose in `README.md` and `CONTRIBUTING.md` so they point at `scripts/README.md` instead of re-explaining the command surface.
2. Update `scripts/README.md` so it clearly owns `doctor`, `clean`, `clean:dry-run`, `clean:deps`, `clean:all`, `reset:data`, and `reset:data:dry-run`.
3. Update `docs/aegis/README.md` to mark this plan as the current active plan.
4. Append the new plan entry to `docs/aegis/INDEX.md`.
5. Run `npm run docs:check` and then commit the docs closure together with the implementation slices.

## Risks and Rollback

- `doctor` may need network access to refresh `origin/main`; if the fetch fails, the command should report that the sync check could not be verified rather than pretending the branch is healthy.
- `reset:data:dry-run` is additive; the destructive `reset:data` command must remain unchanged except for the new preview sibling.
- The cleanup helper already skips `.env`, root `.venv`, and `data/app.db` by default; any change to that boundary needs a matching test before the helper moves.
- Python `3.14` still skips the heavier async-SQLite integration path in the existing API suite, so final verification should not treat that skip as a regression in this plan.
