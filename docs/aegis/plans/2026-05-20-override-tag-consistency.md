# Override Tag Consistency Plan

Date: 2026-05-20

## Goal

Fix the manual review override path so a user can submit `tag_ids` from the detail page without corrupting effective tag display/search data, and prevent manual override preference learning from creating unsafe many-to-one tag mappings.

## Architecture

Manual review flows through:

1. `web/app/repo/RepoDetailClient.tsx` builds a `PATCH /repos/{full_name}/override` payload.
2. `api/app/routes/repos.py` normalizes `OverrideRequest` into an updates dict.
3. `api/app/db/override.py` writes `repos.override_*`, `override_history`, and `training_samples`.
4. `api/app/db/schema.py` triggers rebuild `repo_effective_tags` from `override_tags` and `override_tag_ids`.
5. `api/app/db/search.py` filters repos through `repo_effective_tags`.
6. `api/app/db/user.py` updates global preference hints after successful manual override.

## Tech Stack

- Backend: FastAPI, Pydantic, aiosqlite, pytest.
- Frontend: Next.js, React, TypeScript.
- Storage: SQLite with triggers for derived lookup tables.

## Baseline/Authority Refs

- `docs/aegis/baseline/2026-05-20-initial-baseline.md`
- `api/app/db/override.py`
- `api/app/db/user.py`
- `api/app/routes/repos.py`
- `api/app/db/schema.py`
- `api/tests/test_phase2_route_smoke.py`

## Compatibility Boundary

- Keep `PATCH /repos/{full_name}/override` accepting `tags` and `tag_ids`.
- When only `tag_ids` are supplied, backend must derive matching display tags from taxonomy and store both fields.
- When explicit `tags` are supplied, preserve caller intent while still storing normalized `tag_ids`.
- Keep category/subcategory preference learning.
- Learn tag mapping only when `ai_tag_ids` and `override_tag_ids` are non-empty, have the same length, and every source/target pair is one-to-one after normalization.

## Verification

Run targeted tests first:

```bash
cd /home/aliom/project/StarSorty
pytest api/tests/test_phase2_route_smoke.py api/tests/test_rule_engine.py
```

Run focused regression after implementation:

```bash
cd /home/aliom/project/StarSorty
pytest api/tests/test_phase2_route_smoke.py::test_repos_query_override_and_readme_paths api/tests/test_rule_engine.py
```

Before push, run:

```bash
cd /home/aliom/project/StarSorty
pytest api/tests/test_phase2_route_smoke.py api/tests/test_release_readiness_permissions.py api/tests/test_rule_engine.py
git status -sb
```

## Task 1: Preserve tag display/search consistency for tag_id-only overrides

Files:

- Modify `api/app/db/override.py`.
- Modify `api/app/routes/repos.py` only if route-level taxonomy context is needed.
- Modify `api/tests/test_phase2_route_smoke.py`.

Why:

The detail page submits `tag_ids` only. SQLite derives `repo_effective_tags.tag` from `override_tags`, so `tag_ids` without corresponding `tags` creates mismatched or stale effective tag rows.

Impact/Compatibility:

Existing API callers keep working. `tag_ids` becomes enough for a correct override because backend derives display tags from taxonomy.

Steps:

1. Write RED test in `api/tests/test_phase2_route_smoke.py` that patches a repo override with `tag_ids=["ai.llm","dev.backend"]` and no `tags`, then asserts `update_override` receives both `tag_ids` and derived `tags` display names.
2. Run:

   ```bash
   pytest api/tests/test_phase2_route_smoke.py::test_repos_query_override_and_readme_paths
   ```

   Expected RED: assertion fails because `tags` is absent from captured override updates.
3. Implement minimal backend normalization. Use current taxonomy helpers to map tag IDs to display labels before calling `update_override`.
4. Re-run the same test and confirm GREEN.
5. Commit this task with:

   ```bash
   git add api/app/routes/repos.py api/tests/test_phase2_route_smoke.py
   git commit -m "Keep override tag labels aligned with tag ids"
   ```

## Task 2: Make automatic tag preference learning conservative

Files:

- Modify `api/app/db/user.py`.
- Modify `api/tests/test_rule_engine.py` or add a focused test to the existing user/route smoke coverage.

Why:

Current logic maps each AI tag ID to the override tag ID at the same index, and maps extra AI tags to the last override tag. This can create unsafe many-to-one global mappings from one manual review.

Impact/Compatibility:

Category/subcategory mapping still updates. Tag mapping updates only for unambiguous one-to-one corrections.

Steps:

1. Write RED test proving a mismatched tag count such as AI `["ai.llm","dev.backend"]` and override `["productivity.notes"]` does not add tag mappings, while still allowing category mapping.
2. Add a second assertion for equal-length one-to-one lists such as AI `["ai.llm"]` and override `["ai.agent"]` to keep the intended tag mapping behavior.
3. Run:

   ```bash
   pytest api/tests/test_rule_engine.py
   ```

   Expected RED: mismatched count currently creates tag mappings.
4. Implement a helper in `api/app/db/user.py` that returns tag mapping pairs only when source and target lists are same length and no normalized source/target token repeats.
5. Re-run `pytest api/tests/test_rule_engine.py` and confirm GREEN.
6. Commit this task with:

   ```bash
   git add api/app/db/user.py api/tests/test_rule_engine.py
   git commit -m "Constrain manual override tag preference learning"
   ```

## Task 3: Final regression and sync

Files:

- No production edits expected.

Why:

The change crosses route validation, persistence, search-derived tags, and preference learning. Final verification must cover route behavior and rule/preference tests before pushing.

Steps:

1. Run:

   ```bash
   pytest api/tests/test_phase2_route_smoke.py api/tests/test_release_readiness_permissions.py api/tests/test_rule_engine.py
   ```

2. Run:

   ```bash
   git status -sb
   git log --oneline --decorate --max-count=5
   ```

3. Push:

   ```bash
   git push origin main
   ```

4. Confirm local/remote sync:

   ```bash
   git fetch --prune origin
   git status -sb
   ```

## Risks

- Taxonomy tags can be display names rather than stable IDs; normalization must use the repository's existing taxonomy helpers rather than ad hoc parsing.
- Tests may need lightweight monkeypatching because the route test currently mocks `update_override`.
- If a frontend caller intentionally submits custom display tags without tag IDs, preserve existing behavior.

## Retirement Track

- Retire the old implicit behavior where `override_tag_ids` can be updated alone while `override_tags` remains stale.
- Retire many-to-one automatic tag preference learning.
- Keep existing category/subcategory preference learning and explicit admin preference editing.

