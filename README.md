# StarSorty

Starred repo organizer with a simple API, a static web UI, and a scheduler.

## Features

- Sync starred repos from GitHub (single or multi-user, merged or grouped)
- AI + rules classification with optional README summaries
- Manual overrides with history and stats
- Web UI with filters, repo detail, and quick actions
- Background classification loop + scheduler for periodic sync
- README summaries retry (1-minute backoff, up to 3 attempts)

## Deployment (Docker)

1) Clone the repo on the server

```
git clone https://github.com/aliom-v/StarSorty.git
cd StarSorty
```

2) Copy and edit env file

```
cp .env.example .env
```

Set at least:
- `GITHUB_USERNAME` or `GITHUB_TOKEN`
- `ADMIN_TOKEN` (recommended for write endpoints)
- AI settings if you plan to use classification

3) Build and run

```
docker compose up -d --build
```

4) Access

- Web: http://localhost:1234
- API: http://localhost:4321

5) Sync once

```
curl -X POST http://localhost:4321/sync -H "X-Admin-Token: <ADMIN_TOKEN>"
curl http://localhost:4321/repos
```

## Local dev (Windows)

1) API setup

```
cd api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) Web setup

```
cd ..\web
npm install
```

3) Run both

```
cd ..
npm run dev
```

4) Start/stop/status helpers

```
npm run start   # start API + Web if not running
npm run status  # check listening ports
npm run stop    # stop API + Web
```

## Environment

Core GitHub sync:
- Set `GITHUB_USERNAME` or `GITHUB_TOKEN` in `.env` before syncing.
- Use `GITHUB_TARGET_USERNAME` to sync another user's public stars (token optional).
- Use `GITHUB_USERNAMES` (comma separated) and `GITHUB_MODE=group` to show grouped view.

Admin token:
- If `ADMIN_TOKEN` is set, write endpoints require `X-Admin-Token`.
- The web Settings page stores the token in localStorage and sends it automatically.

Web/API:
- `NEXT_PUBLIC_API_BASE_URL` configures the web UI to reach the API.

Background classification defaults:
- `CLASSIFY_BATCH_SIZE`, `CLASSIFY_CONCURRENCY`, `CLASSIFY_CONCURRENCY_MAX`, `CLASSIFY_BATCH_DELAY_MS`.

## AI classification

The API supports OpenAI, Anthropic, or OpenAI-compatible providers (iflow, glm, etc.).

```
# OpenAI
AI_PROVIDER=openai
AI_API_KEY=your-key
AI_MODEL=gpt-4o-mini

# Anthropic
AI_PROVIDER=anthropic
AI_API_KEY=your-key
AI_MODEL=claude-3-haiku-20240307

# OpenAI-compatible (iflow/glm or custom gateway)
AI_PROVIDER=custom
AI_API_KEY=your-key
AI_MODEL=your-model
AI_BASE_URL=https://your-host/v1
AI_HEADERS_JSON={"X-Custom-Header":"value"}
```

Run classification (foreground):

```
Invoke-RestMethod -Method Post http://localhost:4321/classify -Body '{}' -ContentType 'application/json'
```

Run classification (background):

```
Invoke-RestMethod -Method Post http://localhost:4321/classify/background -Body '{"limit":50,"concurrency":3}' -ContentType 'application/json'
Invoke-RestMethod http://localhost:4321/classify/status
Invoke-RestMethod -Method Post http://localhost:4321/classify/stop
```

Taxonomy file:

- `api/config/taxonomy.yaml` (edit to change categories/tags)
- Set `AI_TAXONOMY_PATH` to override the default taxonomy location.

Rules (optional JSON, stored via Settings):

```
{
  "rules": [
    {
      "keywords": ["music", "spotify", "mp3"],
      "category": "media",
      "subcategory": "music",
      "tags": ["music"]
    },
    {
      "keywords": ["netdisk", "drive", "alist", "s3"],
      "category": "storage",
      "subcategory": "netdisk",
      "tags": ["storage", "netdisk"]
    }
  ]
}
```

## Web UI

- Repo detail page: `/repo?full_name=owner/name`
- Set the admin token in Settings if write actions are protected.

## Services

- api: FastAPI service for sync, status, and data
- web: Next.js static export served by Nginx
- scheduler: cron-like runner that calls /sync

## API endpoints

Write endpoints require `X-Admin-Token` when `ADMIN_TOKEN` is set.

- `POST /sync`: pull starred repos from GitHub
- `GET /repos`: list repos (q, language, min_stars, category, tag, limit, offset)
- `GET /repos/{full_name}`: repo detail
- `PATCH /repos/{full_name}/override`: manual override (category/subcategory/tags/note), empty strings are rejected
- `GET /repos/{full_name}/overrides`: override history
- `POST /repos/{full_name}/readme`: fetch README summary
- `GET /taxonomy`: current taxonomy
- `POST /classify`: AI classification batch
- `POST /classify/background`: background classification loop
- `GET /classify/status`: background classification status
- `POST /classify/stop`: stop background classification
- `GET /settings` / `PATCH /settings`: non-secret runtime settings
- `GET /stats`: repo totals + category/tag/user counts

## Notes

- SQLite file lives in `./data/app.db` by default.
- Logs are written to `./logs/`.
- README summary fetches back off for 1 minute and stop after 3 failed attempts per repo.
