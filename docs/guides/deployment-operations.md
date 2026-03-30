# 部署与运维

本文档聚焦 Docker Compose 部署、目录持久化、升级流程以及常见运维动作。
本地开发、测试命令和 Python/Docker fallback 细节统一见 `../../scripts/README.md` 与 `../../CONTRIBUTING.md`，这里不再重复维护同一套运行手册。

当前推荐形态是单机 VPS 直接运行 `docker compose`。`web` 容器会以 Next.js 服务端运行时提供页面，不再依赖单独的静态托管平台。

## 服务组成

`docker-compose.yml` 当前包含 3 个服务：

- `api`：FastAPI 后端，监听宿主机 `4321`
- `web`：Next.js Web 服务，监听宿主机 `1234`
- `scheduler`：APScheduler 定时触发 `/sync`

默认持久化目录：

- `data/`：SQLite 数据库
- `logs/`：运行日志

## VPS 规格建议

- `1C1G / 20G`：低访问量、低频同步、偶发分类任务
- `2C2G / 20G+`：更推荐，镜像构建、批量分类和长时间运行更稳
- 无论哪种规格，都要持久化 `data/` 与 `logs/`

## 快速部署

### 1. 准备环境变量

```bash
cp .env.example .env
```

至少配置：

- `API_BASE_URL`
- `NEXT_PUBLIC_API_BASE_URL`
- `CORS_ORIGINS`

按目标追加：

- 只验证容器与首页：默认模板即可，但不会有仓库数据，`/auth/check` 会因为 `ADMIN_TOKEN` 为空返回 `503`。
- 需要本地管理写操作：配置 `ADMIN_TOKEN`；如果只是受信任的本地开发，也可保持 `APP_ENV=development` 并临时开启 `ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV=true`。
- 需要首次同步：至少提供一个 GitHub 目标。可配置 `GITHUB_USERNAME`、`GITHUB_TARGET_USERNAME`、`GITHUB_USERNAMES`；也可只配置 `GITHUB_TOKEN`，系统会自动把 token 对应账号作为同步目标。`GITHUB_TOKEN` 强烈建议配置以避免限流。
- 需要 AI 分类：`CLASSIFY_MODE=rules_only` 可直接使用内置规则；`rules_then_ai` 在缺少 AI 配置时会退回规则分类；`ai_only` 必须补齐 `AI_PROVIDER`、`AI_MODEL` 以及对应密钥或 `AI_BASE_URL`。
- 需要公网部署：务必配置强随机 `ADMIN_TOKEN`，并把浏览器访问链路收敛到显式域名与 HTTPS。

推荐约定：

- `API_BASE_URL` 保持 `http://api:4321`，供 scheduler 与 SSR Web 走容器内网络
- `NEXT_PUBLIC_API_BASE_URL` 填浏览器实际访问的地址；如果前面有同域反向代理，优先直接设成 `/api`
- Web 管理台依赖 cookie session，最好让 Web 和 API 处于同域或 same-site 域名下

### 2. 启动

```bash
docker compose up -d --build
```

### 3. 检查状态

```bash
docker compose ps
curl http://localhost:4321/health
curl http://localhost:1234
```

### 4. 首次同步与分类

在执行下面两条命令前，至少确认：

- `POST /sync` 不会再因为管理员鉴权返回 `503`
- 已经配置至少一个 GitHub 同步目标，否则任务会失败并提示 `No GitHub usernames configured`
- 如果当前是 `CLASSIFY_MODE=ai_only`，AI 配置已经完整；否则后台分类会失败

```bash
curl -X POST "http://localhost:4321/sync" \
  -H "X-Admin-Token: <ADMIN_TOKEN>"

curl -X POST "http://localhost:4321/classify/background" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: <ADMIN_TOKEN>" \
  -d '{"limit":50,"concurrency":3}'
```

如果当前没有 `GITHUB_TOKEN`，建议首次先避免 README 抓取，降低匿名速率限制影响：

```bash
curl -X POST "http://localhost:4321/classify/background" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: <ADMIN_TOKEN>" \
  -d '{"limit":50,"concurrency":3,"include_readme":false}'
```

## 目录与数据

### `data/`

- 包含 SQLite 数据库文件
- 记录仓库元数据、任务状态、用户偏好、设置覆盖等信息
- 升级前应优先备份该目录

### `logs/`

- 保存 API / 脚本相关日志输出
- 建议接入宿主机日志轮转，避免长期增长

## 反向代理建议

若通过 Nginx / Caddy / Traefik 暴露到公网：

- Web 域名例如 `https://stars.example.com`
- API 域名例如 `https://stars-api.example.com`，或同域反代到 `/api`
- `NEXT_PUBLIC_API_BASE_URL` 设置为浏览器可访问的 API 公网地址或 `/api`
- 如果浏览器需要使用管理台，优先同域反代 `/api`；若拆成子域，也应保持 same-site 域名
- `API_BASE_URL` 继续保持容器内地址，例如 `http://api:4321`
- `CORS_ORIGINS` 设置为 Web 实际来源，例如 `https://stars.example.com`
- 不要把 `4321` 直接裸露到公网而没有反向代理或访问控制

### Nginx 同域 `/api` 示例

仓库内可直接复用的模板见 `../../deploy/nginx/starsorty.conf.example`。下面是同一份最小示例：

```nginx
server {
    listen 80;
    server_name stars.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name stars.example.com;

    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:4321/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://127.0.0.1:1234/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

对应环境变量建议：

```env
APP_ENV=production
CORS_ORIGINS=https://stars.example.com
API_BASE_URL=http://api:4321
NEXT_PUBLIC_API_BASE_URL=/api
```

说明：

- 浏览器访问统一走 `https://stars.example.com`
- Next.js 页面请求会走同域 `/api`
- `API_BASE_URL` 仍保留容器内地址，供 scheduler 和 SSR 使用
- `APP_ENV=production` 时管理员 session cookie 会带 `Secure`；如果浏览器仍通过 HTTP 打开管理台，登录后 cookie 不会稳定写入

### 验证同域 `/api` 与管理员会话是否生效

建议在浏览器里按下面顺序检查：

1. 打开 `https://stars.example.com/admin`
2. 输入 `ADMIN_TOKEN` 登录
3. 在浏览器开发者工具的 Cookie 面板确认存在：
   - `starsorty_admin_session`
   - `starsorty_admin_csrf`
4. 触发一次 `Sync` 或后台分类，在 Network 面板确认请求：
   - URL 落在 `https://stars.example.com/api/...`
   - 响应不是 `401`
   - 请求头带有 `X-CSRF-Token`

如果登录成功但写操作仍然 `401`，优先检查：

- 浏览器是否仍在用 `http://` 而不是 `https://`
- `NEXT_PUBLIC_API_BASE_URL` 是否仍指向错误域名
- Web 与 API 是否已经变成跨站点，而不是同域 `/api` 或 same-site 域名
- 最近修改 `NEXT_PUBLIC_API_BASE_URL` 后是否已重建 Web 镜像

## 生产环境清单

- `APP_ENV=production`
- `ADMIN_TOKEN` 已配置且强随机
- `ADMIN_SESSION_TTL_HOURS` 已按运维要求设置
- 不要以默认 development 环境直接对外暴露实例
- 浏览器管理台在 production 模式下应通过 HTTPS 访问
- `CORS_ORIGINS` 为明确来源列表
- 浏览器管理台访问路径已验证 cookie 可写入，且 Web/API 处于同域或 same-site 域名
- `GITHUB_TOKEN` 与 AI key 已配置
- `API_BASE_URL` 仍指向容器内 `http://api:4321`
- `data/` 已做持久化挂载
- `logs/` 已纳入日志收集或轮转
- 变更 `NEXT_PUBLIC_API_BASE_URL` 后已重新构建 Web 镜像
- 定期备份数据库文件

## 升级流程

推荐升级步骤：

1. 备份 `data/`
2. 拉取新代码
3. 对比 `.env.example` 与现有 `.env`
4. 重新构建并启动容器
5. 检查 `/health`、Web 首页与后台分类状态

示例：

```bash
cp -r data data.backup.$(date +%Y%m%d-%H%M%S)
git pull
docker compose up -d --build
docker compose ps
```

## 备份与恢复

### 备份

最小备份集：

- `data/`
- `.env`

示例：

```bash
tar czf starsorty-backup-$(date +%Y%m%d).tar.gz data .env
```

### 恢复

1. 停止服务
2. 恢复 `data/` 与 `.env`
3. 重新启动容器

```bash
docker compose down
tar xzf starsorty-backup-20260307.tar.gz
docker compose up -d
```

## 常见运维动作

### 查看日志

```bash
docker compose logs -f api
docker compose logs -f web
docker compose logs -f scheduler
```

说明：

- API 日志现在会附带 `request_id` 与 `task_id` 字段；可结合响应头 `X-Request-ID` 反查一次请求对应的后端日志。
- 对于 `POST /sync`、`POST /classify/background`、`POST /tasks/{task_id}/retry` 等异步任务，返回体中的 `task_id` 可直接与日志中的 `task_id` 对应。

### 手动停止后台分类

```bash
curl -X POST "http://localhost:4321/classify/stop" \
  -H "X-Admin-Token: <ADMIN_TOKEN>"
```

返回说明：

- `{"stopped": true}`：已接受停止请求，任务会在当前批次结束后进入 `stopped` 终态
- `{"stopped": false}`：当前进程没有活跃后台分类任务

补充：

- 停止请求会写入 SQLite 共享运行态；即使请求落到非执行分类循环的 worker，也会在下一批次边界生效

### 导出 Obsidian 包

```bash
curl -L "http://localhost:4321/export/obsidian?language=Python&tags=rag,agent" \
  -H "X-Admin-Token: <ADMIN_TOKEN>" \
  -o starsorty-export.zip
```

说明：

- 导出响应现在为流式 ZIP；下载会在服务端生成过程中开始返回数据，不再先整包聚合到内存

## 故障定位手册

### 1. 同步失败

建议按下面顺序排查：

1. 重新触发一次同步，并记录响应头里的 `X-Request-ID` 与返回体里的 `task_id`
2. 查询任务状态：`GET /tasks/{task_id}`
3. 查看最近日志，按 `request_id` 或 `task_id` 过滤
4. 查看 `/metrics/quality` 中的 `task_failed_total`、`api_error_rate`、`db_lock_conflict_total`

示例：

```bash
curl -i -X POST "http://localhost:4321/sync" \
  -H "X-Admin-Token: <ADMIN_TOKEN>"

curl "http://localhost:4321/tasks/<task_id>"

docker compose logs --since=10m api | rg "<task_id>|<request_id>"

curl "http://localhost:4321/metrics/quality"
```

优先关注：

- GitHub token 是否失效、额度是否耗尽
- `update_sync_status` 返回的错误信息是否指向 GitHub API / 网络异常
- `db_lock_conflict_total`、`db_lock_retry_exhausted_total` 是否持续增长；若是，转到“SQLite 锁冲突”章节继续排查

### 2. 分类失败或长时间不推进

建议按下面顺序排查：

1. 触发后台分类时，先记录 `POST /classify/background` 返回体里的 `task_id`
2. 查看 `GET /classify/status`，确认 `status/running/processed/remaining/last_error`
3. 如果当前仍在运行，`/classify/status` 里的 `task_id` 可继续用于追踪；任务结束后请优先使用最初返回的 `task_id`
4. 查询 `GET /tasks/{task_id}`
5. 用 `task_id` 或该次请求的 `X-Request-ID` 过滤 API 日志
6. 查看 `/metrics/quality` 中的 `task_failed_total`、`task_failure_rate`

示例：

```bash
curl "http://localhost:4321/classify/status"

curl "http://localhost:4321/tasks/<task_id>"

docker compose logs --since=10m api | rg "<task_id>|<request_id>|Background classification"
```

优先关注：

- `CLASSIFY_MODE` 是否误设为 `rules_only` 或 `ai_only`
- AI provider、`AI_API_KEY`、`AI_MODEL` 是否完整
- 如果没配 `GITHUB_TOKEN`，是否因为 `include_readme=true` 触发了 GitHub README 抓取限流
- taxonomy / rules 文件路径是否可读
- `status` 是否停在 `queued` / `running`
- `last_error` 是否显示批量 AI 失败、回退失败，或在人工停止后落成 `Stopped by user`
- 若使用多 worker，`/classify/status`、`/metrics/quality` 与 `/stats` 现在都应直接通过 SQLite 共享；`/repos` 也应能跨 worker 复用同一份缓存值。若仍出现旧数据，优先确认是否有旧 worker 未重启，或共享 SQLite 文件并不一致

若任务已失败但希望继续，可执行：

```bash
curl -X POST "http://localhost:4321/tasks/<task_id>/retry" \
  -H "X-Admin-Token: <ADMIN_TOKEN>"
```

### 3. SQLite 锁冲突或后台吞吐明显下降

建议先看指标，再决定是配置问题还是短时写入高峰：

```bash
curl "http://localhost:4321/metrics/quality"

docker compose logs --since=15m api | rg "locked|retry|task_status_updated"
```

优先关注：

- `db_lock_conflict_total`：已经观察到多少次锁冲突
- `db_lock_retry_total`：进入退避重试的次数
- `db_lock_retry_exhausted_total`：重试后仍失败的次数
- `task_queued_total` / `task_failed_total`：锁冲突是否已经拖垮后台任务成功率

处理建议：

- 避免同步与大批量分类同时压在同一个 SQLite 写路径上
- 下调 `CLASSIFY_CONCURRENCY`
- 如果是大账号同步，等待当前批次完成后再继续触发新任务
- 若指标持续增长且任务恢复不了，优先保留 `request_id/task_id` 和最近日志，再考虑重启服务

## 常见问题

### API 容器启动失败

优先检查：

- `APP_ENV` 与 `ADMIN_TOKEN`
- `CORS_ORIGINS`
- `.env` 是否被正确挂载

### Web 能打开，但请求 API 失败

优先检查：

- `NEXT_PUBLIC_API_BASE_URL` 是否正确，且修改后是否已经 `docker compose up -d --build web`
- 浏览器控制台是否有 CORS 报错
- 若当前是 production，浏览器是否通过 HTTPS 访问 Web
- `api` 服务健康检查是否通过
- 失败请求返回的 `X-Request-ID` 是否能在 `docker compose logs -f api` 中定位到对应日志

### scheduler 没有定时触发

优先检查：

- `SYNC_CRON` 是否合法
- `API_BASE_URL` 是否指向 `http://api:4321`
- `ADMIN_TOKEN` 是否与 API 保持一致

### 动态详情页打开 500 或首屏报错

优先检查：

- `web` 容器内 `API_BASE_URL` 是否仍然是 `http://api:4321`
- `api` 服务是否健康
- `docker compose logs --since=10m web` 中是否有服务端抓取 `/repos/{full_name}` 的报错

### 本地验证脚本失败

这类问题不再在运维文档里重复展开。若失败发生在宿主机本地执行 `npm run api:test`、`npm run web:lint`、`npm run web:build`、`npm run web:smoke` 等命令时，直接按 `../../scripts/README.md` 与 `../../CONTRIBUTING.md` 排查。

### 分类结果长时间没有变化

优先检查：

- AI provider 配置是否完整
- `CLASSIFY_MODE` 是否为 `rules_only`
- `/classify/status` 与 `/tasks/{task_id}` 是否有失败信息
- API 日志中的 `task_id` / `request_id` 是否显示分类任务已进入失败或重试路径
