# Initial Baseline: Override Tag Consistency

Date: 2026-05-20

StarSorty is a Next.js frontend plus FastAPI backend that stores GitHub star metadata in SQLite.

Relevant architecture facts:

- `web/app/repo/RepoDetailClient.tsx` owns the repository detail manual review form.
- `api/app/routes/repos.py` owns `PATCH /repos/{full_name}/override` request validation and cache invalidation.
- `api/app/db/override.py` owns persistence for `override_*`, `override_history`, and `training_samples`.
- `api/app/db/schema.py` maintains `repo_effective_tags` from `ai_tags`/`ai_tag_ids` and `override_tags`/`override_tag_ids`.
- `api/app/db/search.py` uses `repo_effective_tags` for tag filtering.
- `api/app/db/user.py` owns manual override preference learning for the global user.
- `api/config/taxonomy.yaml` defines category/subcategory names and display tag labels.

Compatibility boundary:

- Existing override API callers may submit `tags`, `tag_ids`, both, or neither.
- Existing `override_history` and `training_samples` rows must remain readable.
- Category/subcategory preference learning remains active.
- Automatic tag mapping learning must not create many-to-one mappings from ambiguous manual reviews.

