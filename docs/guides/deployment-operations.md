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

## 相关阅读

- `docs/README.md`
- `docs/guides/configuration.md`
- `docs/guides/api-reference.md`
- `docker-compose.yml`
