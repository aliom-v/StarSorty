# 部署与运维

本文档聚焦 Docker Compose 部署、目录持久化、升级流程以及常见运维动作。

## 服务组成

`docker-compose.yml` 当前包含 3 个服务：

- `api`：FastAPI 后端，监听宿主机 `4321`
- `web`：Next.js 静态站点 + Nginx，监听宿主机 `1234`
- `scheduler`：APScheduler 定时触发 `/sync`

默认持久化目录：

- `data/`：SQLite 数据库
- `logs/`：运行日志

## 快速部署

### 1. 准备环境变量

```bash
cp .env.example .env
```

至少配置：

- `GITHUB_TOKEN`
- `ADMIN_TOKEN`
- `AI_PROVIDER` / `AI_API_KEY` / `AI_MODEL`（如需 AI 分类）
- `NEXT_PUBLIC_API_BASE_URL`
- `CORS_ORIGINS`

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

```bash
curl -X POST "http://localhost:4321/sync" \
  -H "X-Admin-Token: <ADMIN_TOKEN>"

curl -X POST "http://localhost:4321/classify/background" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: <ADMIN_TOKEN>" \
  -d '{"limit":50,"concurrency":3}'
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
- API 域名例如 `https://stars-api.example.com`
- `NEXT_PUBLIC_API_BASE_URL` 设置为浏览器可访问的 API 公网地址
- `CORS_ORIGINS` 设置为 Web 实际来源，例如 `https://stars.example.com`
- 不要把 `4321` 直接裸露到公网而没有反向代理或访问控制

## 生产环境清单

- `APP_ENV=production`
- `ADMIN_TOKEN` 已配置且强随机
- `CORS_ORIGINS` 为明确来源列表
- `GITHUB_TOKEN` 与 AI key 已配置
- `data/` 已做持久化挂载
- `logs/` 已纳入日志收集或轮转
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

### 导出 Obsidian 包

```bash
curl -L "http://localhost:4321/export/obsidian?language=Python&tags=rag,agent" \
  -H "X-Admin-Token: <ADMIN_TOKEN>" \
  -o starsorty-export.zip
```

### 运行 API 测试与压测脚本

```bash
npm run api:test
npm run api:bench
```

两者都会优先使用本地可用 Python；若当前环境不适合运行，会自动回退到 Docker Python 3.11 容器。

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

1. 查看 `GET /classify/status`，确认 `running/processed/remaining/last_error/task_id`
2. 如果已有 `task_id`，继续查 `GET /tasks/{task_id}`
3. 用 `task_id` 或该次请求的 `X-Request-ID` 过滤 API 日志
4. 查看 `/metrics/quality` 中的 `task_failed_total`、`task_failure_rate`

示例：

```bash
curl "http://localhost:4321/classify/status"

curl "http://localhost:4321/tasks/<task_id>"

docker compose logs --since=10m api | rg "<task_id>|<request_id>|Background classification"
```

优先关注：

- `CLASSIFY_MODE` 是否误设为 `rules_only` 或 `ai_only`
- AI provider、`AI_API_KEY`、`AI_MODEL` 是否完整
- taxonomy / rules 文件路径是否可读
- `last_error` 是否显示批量 AI 失败、回退失败或人工停止

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

### 4. Web lint / build 失败

建议按下面顺序排查：

```bash
npm --prefix web run lint
npm --prefix web run build
```

优先关注：

- `web/node_modules` 是否完整；如果出现 `eslint: command not found`、`next: command not found` 之类错误，先执行 `cd web && npm install`
- `NEXT_PUBLIC_API_BASE_URL` 是否仍然指向正确 API 地址
- 最近是否改动了首页拆分相关共享类型、组件 props 或 i18n key
- CI 中是否仅 `lint` 失败、仅 `build` 失败，还是两者都失败

如果是部署后才暴露问题，再补看：

```bash
docker compose logs --since=10m web
```

## 常见问题

### API 容器启动失败

优先检查：

- `APP_ENV` 与 `ADMIN_TOKEN`
- `CORS_ORIGINS`
- `.env` 是否被正确挂载

### Web 能打开，但请求 API 失败

优先检查：

- `NEXT_PUBLIC_API_BASE_URL` 是否正确
- 浏览器控制台是否有 CORS 报错
- `api` 服务健康检查是否通过
- 失败请求返回的 `X-Request-ID` 是否能在 `docker compose logs -f api` 中定位到对应日志

### scheduler 没有定时触发

优先检查：

- `SYNC_CRON` 是否合法
- `API_BASE_URL` 是否指向 `http://api:4321`
- `ADMIN_TOKEN` 是否与 API 保持一致

### 分类结果长时间没有变化

优先检查：

- AI provider 配置是否完整
- `CLASSIFY_MODE` 是否为 `rules_only`
- `/classify/status` 与 `/tasks/{task_id}` 是否有失败信息
- API 日志中的 `task_id` / `request_id` 是否显示分类任务已进入失败或重试路径

## 相关阅读

- `docs/README.md`
- `docs/guides/configuration.md`
- `docs/guides/api-reference.md`
- `docker-compose.yml`
