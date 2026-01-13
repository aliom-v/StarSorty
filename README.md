# StarSorty

Starred repo organizer with a simple API, a static web UI, and a scheduler.

## Quick start

1) Copy env file

```
cp .env.example .env
```

2) Build and run

```
docker compose up -d --build
```

3) Open

- Web: http://localhost:3000
- API: http://localhost:8000

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

## Start/stop/status helpers

```
npm run start   # start API + Web if not running
npm run status  # check listening ports
npm run stop    # stop API + Web
```

4) Sync data

```
Invoke-RestMethod -Method Post http://localhost:8000/sync
Invoke-RestMethod http://localhost:8000/repos
```

Notes:
- Set `GITHUB_USERNAME` or `GITHUB_TOKEN` in `.env` before syncing.
- Use `GITHUB_TARGET_USERNAME` to sync another user's public stars (token optional).
- Use `GITHUB_USERNAMES` (comma separated) for multiple users and `GITHUB_MODE=group` to show grouped view.
- Configure AI env vars before running `/classify`.

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

Run classification:

```
Invoke-RestMethod -Method Post http://localhost:8000/classify -Body '{}' -ContentType 'application/json'
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

## Services

- api: FastAPI service for sync, status, and data
- web: Next.js static export served by Nginx
- scheduler: cron-like runner that calls /sync

## API endpoints

- `POST /sync`: pull starred repos from GitHub
- `GET /repos`: list repos (q, language, min_stars, category, tag, limit, offset)
- `GET /repos/{full_name}`: repo detail
- `PATCH /repos/{full_name}/override`: manual override (category/subcategory/tags/note)
- `POST /repos/{full_name}/readme`: fetch README summary
- `GET /taxonomy`: current taxonomy
- `POST /classify`: AI classification batch
- `GET /settings` / `PATCH /settings`: non-secret runtime settings

## Notes

- SQLite file lives in ./data/app.db by default
- Logs are written to ./logs/
