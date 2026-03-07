# 配置参考

本文档说明 StarSorty 的运行配置来源、环境变量分组，以及哪些配置可以通过 Web / API 动态修改。

## 配置来源与优先级

StarSorty 目前有两类配置来源：

1. 根目录 `.env`
2. SQLite 中的 `app_settings` 覆盖项（由 `PATCH /settings` 写入）

优先级规则：

- 非敏感业务配置：优先读取 `app_settings`，不存在时回退到 `.env`
- 敏感配置：仅从 `.env` 读取，不会写入数据库

仅从 `.env` 读取的敏感项包括：

- `GITHUB_TOKEN`
- `AI_PROVIDER`
- `AI_API_KEY`
- `AI_MODEL`
- `AI_BASE_URL`
- `AI_HEADERS_JSON`
- `AI_TEMPERATURE`
- `AI_MAX_TOKENS`
- `AI_TIMEOUT`
- `AI_TAXONOMY_PATH`
- `DATABASE_URL`
- `CORS_ORIGINS`
- `LOG_LEVEL`
- 各类特性开关与限流参数

## 基础推荐配置

最小可运行示例：

```env
GITHUB_USERNAME=your_name
GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
ADMIN_TOKEN=change_me
APP_ENV=development
CORS_ORIGINS=http://localhost:1234

AI_PROVIDER=custom
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=sk-xxxx
AI_MODEL=deepseek-chat
```

## 环境变量分组

### GitHub 目标与同步来源

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GITHUB_USERNAME` | 空 | 主同步用户名。 |
| `GITHUB_TARGET_USERNAME` | 空 | 额外同步用户名。 |
| `GITHUB_USERNAMES` | 空 | 多用户名列表，支持逗号或换行。 |
| `GITHUB_INCLUDE_SELF` | `false` | 有 token 时是否自动把认证用户纳入同步目标。 |
| `GITHUB_MODE` | `merge` | 多目标合并策略，支持 `merge` / `group`。 |
| `GITHUB_TOKEN` | 空 | GitHub API token，建议始终配置以避免限流。 |
| `GITHUB_API_BASE_URL` | `https://api.github.com` | GitHub Enterprise 或代理地址。 |

### 管理与安全

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ADMIN_TOKEN` | 空 | 管理写接口鉴权 token。 |
| `APP_ENV` | `development` | 运行环境；设为 `production` 会启用严格安全校验。 |
| `CORS_ORIGINS` | `http://localhost:1234` | 允许跨域来源，生产环境必须是明确列表，不能为 `*`。 |
| `LOG_LEVEL` | `INFO` | API 与 scheduler 日志级别。 |

### 分类与规则

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CLASSIFY_MODE` | `ai_only` | 支持 `rules_then_ai`、`ai_only`、`rules_only`。 |
| `AUTO_CLASSIFY_AFTER_SYNC` | `true` | 同步后是否自动触发分类。 |
| `AI_TAXONOMY_PATH` | `api/config/taxonomy.yaml` | 自定义 taxonomy 文件路径。 |
| `RULES_JSON` | 空 | JSON 字符串形式的规则覆盖。 |
| `RULE_DIRECT_THRESHOLD` | `0.88` | 规则直接命中阈值。 |
| `RULE_AI_THRESHOLD` | `0.45` | 规则进入 AI 仲裁阈值。 |

### AI Provider

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AI_PROVIDER` | `none` | 支持 `openai`、`anthropic`、`custom`、`none`。 |
| `AI_API_KEY` | 空 | 模型服务密钥。 |
| `AI_MODEL` | 空 | 模型名称。 |
| `AI_BASE_URL` | 空 | 自定义 OpenAI 兼容接口地址。 |
| `AI_HEADERS_JSON` | 空 | 额外请求头，JSON 字符串。 |
| `AI_TEMPERATURE` | `0.2` | 温度参数。 |
| `AI_MAX_TOKENS` | `500` | 输出 token 上限。 |
| `AI_TIMEOUT` | `30` | AI 请求超时秒数。 |

### 调度、任务与存储

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SYNC_CRON` | `0 */6 * * *` | scheduler 触发同步的 cron 表达式，使用 UTC。 |
| `SYNC_TIMEOUT` | `30` | scheduler 调用 `/sync` 的超时秒数。 |
| `DATABASE_URL` | `sqlite:////data/app.db` | 当前仅支持 SQLite。 |
| `API_BASE_URL` | `http://api:4321` | scheduler 容器访问 API 的内部地址。 |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:4321` | Web 构建时注入的 API 地址。 |

### 批处理与性能

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CLASSIFY_BATCH_SIZE` | `50` | 后台分类默认批次大小。 |
| `CLASSIFY_CONCURRENCY` | `3` | 后台分类默认并发数。 |
| `CLASSIFY_CONCURRENCY_MAX` | `10` | 后台分类并发上限。 |
| `CLASSIFY_BATCH_DELAY_MS` | `0` | 批次间延迟。 |
| `RELEVANCE_CANDIDATE_LIMIT` | `2000` | 相关度重排候选集上限。 |
| `STAR_USER_LOOKUP_CHUNK_SIZE` | `400` | 同步时按用户回填 Star 关系的分批大小。 |
| `TAXONOMY_CACHE_TTL_SECONDS` | `300` | taxonomy 进程内缓存 TTL。 |
| `RULES_CACHE_TTL_SECONDS` | `300` | rules 进程内缓存 TTL。 |

### 限流

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `RATE_LIMIT_DEFAULT` | `60/minute` | 默认接口限流。 |
| `RATE_LIMIT_ADMIN` | `30/minute` | 管理接口限流。 |
| `RATE_LIMIT_HEAVY` | `10/minute` | 高成本接口限流，例如同步、分类、导出。 |

### 重构与实验性开关

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CLASSIFY_ENGINE_V2_ENABLED` | `1` | 启用新版分类链路。 |
| `SEARCH_RANKER_V2_ENABLED` | `1` | 启用新版搜索重排与命中解释。 |

## 通过 API 可修改的配置

`PATCH /settings` 当前支持更新以下字段，并持久化到 SQLite：

- `github_username`
- `github_target_username`
- `github_usernames`
- `github_include_self`
- `github_mode`
- `classify_mode`
- `auto_classify_after_sync`
- `rules_json`
- `sync_cron`
- `sync_timeout`

注意：

- `GITHUB_TOKEN`、`AI_API_KEY` 等敏感配置不会通过该接口暴露或写入。
- `GET /settings` 为管理员接口，返回的是“当前生效配置 + token 是否已配置”，不是完整 secrets 明文。
- 前端公开页面应使用 `GET /api/config/client-settings`，该接口仅返回安全字段。

## 生产环境建议

- 将 `APP_ENV` 设为 `production`。
- 配置强随机 `ADMIN_TOKEN`。
- 将 `CORS_ORIGINS` 设置为显式域名列表，不要使用 `*`。
- 如果使用反向代理，保持 `NEXT_PUBLIC_API_BASE_URL` 指向对浏览器可达的公开 API 地址。
- 为 `data/` 与 `logs/` 目录做持久化与备份。

## 常见配置组合

### 只用规则分类，不接第三方模型

```env
CLASSIFY_MODE=rules_only
AI_PROVIDER=none
AUTO_CLASSIFY_AFTER_SYNC=true
```

### 规则优先，命中不足时再回退 AI

```env
CLASSIFY_MODE=rules_then_ai
AI_PROVIDER=openai
AI_API_KEY=sk-xxxx
AI_MODEL=gpt-4o-mini
RULE_DIRECT_THRESHOLD=0.88
RULE_AI_THRESHOLD=0.45
```

### 多用户 Star 聚合

```env
GITHUB_USERNAMES=alice,bob,charlie
GITHUB_MODE=merge
```

## 故障排查

- API 启动时提示 `ADMIN_TOKEN is required in production mode`：说明 `APP_ENV=production` 但未配置 `ADMIN_TOKEN`。
- API 启动时提示 `CORS_ORIGINS must be an explicit origin list`：说明生产环境仍使用了通配符或空值。
- Web 页面请求错地址：检查 `NEXT_PUBLIC_API_BASE_URL` 是否与部署域名一致。
- scheduler 无法触发同步：检查 `API_BASE_URL`、`SYNC_CRON` 与 `ADMIN_TOKEN` 是否在 scheduler 容器内生效。

## 相关阅读

- `docs/README.md`
- `docs/guides/deployment-operations.md`
- `docs/guides/api-reference.md`
- `.env.example`
