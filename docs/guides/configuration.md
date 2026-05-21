# 配置参考

本文档说明 StarSorty 的运行配置来源、环境变量分组，以及哪些配置可以通过 Web / API 动态修改。

## 配置来源与优先级

StarSorty 目前有两类配置来源：

1. 根目录 `.env`
2. SQLite 中的 `app_settings` 覆盖项（由 `PATCH /settings` 写入）

优先级规则：

- 非敏感业务配置：优先读取 `app_settings`，不存在时回退到 `.env`
- 敏感配置：仅从 `.env` 读取，不会写入数据库
- API 进程会缓存最近一次解析出的配置快照；当 `PATCH /settings` 写入成功后，当前进程会立即失效并重建该快照

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

## 按能力补配置

| 目标 | 需要补齐什么 | 结果 |
| --- | --- | --- |
| 启动 Compose、检查 `/health`、打开首页 | 默认模板即可，至少保证 `API_BASE_URL`、`NEXT_PUBLIC_API_BASE_URL`、`CORS_ORIGINS` 符合当前访问方式 | 服务可以启动，但仓库数据为空，管理员写接口在 `ADMIN_TOKEN` 缺失时会返回 `503`。 |
| 本地开发时测试管理写操作 | `ADMIN_TOKEN`；或仅在 `APP_ENV=development` 下临时开启 `ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV=true` | 可继续访问 `POST /sync`、`POST /classify/background`、`PATCH /settings` 等管理接口。生产环境不能使用该豁免。 |
| 首次同步 GitHub Star | 至少一个同步目标：`GITHUB_USERNAME`、`GITHUB_TARGET_USERNAME`、`GITHUB_USERNAMES` 三者任选其一；或只配置 `GITHUB_TOKEN`，系统会把认证用户自己作为目标 | 没有任何目标时，`/sync` 会失败并提示 `No GitHub usernames configured`。`GITHUB_TOKEN` 不是强制项，但强烈建议配置以避免限流。 |
| 把 token 对应账号附加到现有用户名列表 | 在已有显式用户名的基础上，再设 `GITHUB_INCLUDE_SELF=true` 并提供 `GITHUB_TOKEN` | 同时同步显式用户名列表和 token 对应账号。 |
| 只做规则分类 | `CLASSIFY_MODE=rules_only`，AI 配置可为空 | 使用内置 `api/config/rules.json`；只有在规则文件本身不可用时，才需要额外补 `RULES_JSON`。 |
| 规则优先，必要时再用 AI | `CLASSIFY_MODE=rules_then_ai`，可选补 `AI_PROVIDER`、`AI_MODEL` 以及对应密钥或 `AI_BASE_URL` | AI 配置完整时走规则 + AI 仲裁；AI 缺失但规则可用时，自动退回 `rules_only`。 |
| 强制纯 AI 分类 | `CLASSIFY_MODE=ai_only`，并补齐 `AI_PROVIDER`、`AI_MODEL`，以及 `AI_API_KEY`（`openai` / `anthropic`）或 `AI_BASE_URL`（自定义 provider） | AI 配置不完整时，分类会失败；自动回退场景只会在允许 fallback 的内部链路中发生。 |

## 环境变量分组

### GitHub 目标与同步来源

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GITHUB_USERNAME` | 空 | 主同步用户名。 |
| `GITHUB_TARGET_USERNAME` | 空 | 额外同步用户名。 |
| `GITHUB_USERNAMES` | 空 | 多用户名列表，支持逗号或换行。 |
| `GITHUB_INCLUDE_SELF` | `false` | 有 token 时是否自动把认证用户纳入同步目标。 |
| `GITHUB_MODE` | `merge` | 多目标合并策略，支持 `merge` / `group`。 |
| `GITHUB_TOKEN` | 空 | GitHub API token，建议始终配置以避免限流；未配置时，同步通常仍可依赖公开接口或显式用户名运行，但 README 抓取更容易撞到匿名速率限制。 |
| `GITHUB_API_BASE_URL` | `https://api.github.com` | GitHub Enterprise 或代理地址。 |

目标解析规则：

- 先读取 `GITHUB_USERNAMES`，再附加 `GITHUB_TARGET_USERNAME` 与 `GITHUB_USERNAME`。
- 如果已经配置了显式用户名，只有在 `GITHUB_INCLUDE_SELF=true` 且 `GITHUB_TOKEN` 存在时，才会把认证用户自己追加进去。
- 如果没有任何显式用户名，但配置了 `GITHUB_TOKEN`，系统会自动请求 `/user` 并把该认证账号作为唯一同步目标。
- 如果显式用户名和 `GITHUB_TOKEN` 都没有，`/sync` 会直接失败。

### 管理与安全

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ADMIN_TOKEN` | 空 | 管理写接口鉴权 token。 |
| `ADMIN_SESSION_TTL_HOURS` | `12` | Web 管理台把 `ADMIN_TOKEN` 交换成浏览器 cookie 会话后的有效时长。 |
| `ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV` | `false` | 仅限本地开发的管理员豁免开关；只有未进入 production 且显式开启时才会生效。 |
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
| `RULE_DIRECT_THRESHOLD` | `0.88` | 规则高置信度直接命中阈值。 |
| `RULE_AI_THRESHOLD` | `0.45` | 规则进入 AI 仲裁阈值；达到该值时会把候选规则一起交给 AI 参考。 |
| `RULE_MIN_THRESHOLD` | `0.42` | 规则最低可信阈值；低于该值的命中不会再直接回退到规则。 |
| `RULE_AMBIGUITY_GAP` | `0.08` | 前两名不同分类候选的最小安全分差；过近时会转 AI 或 manual review。 |
| `CLASSIFY_README_DESCRIPTION_MIN_CHARS` | `120` | 描述短于该长度时，分类前会优先补 README 摘要。 |
| `CLASSIFY_README_MIN_TOPICS` | `2` | topics 少于该数量时，分类前会优先补 README 摘要。 |

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
| `DATABASE_URL` | `sqlite:////data/app.db` | 当前仅支持 SQLite；该默认值对应 Docker / Compose 容器内的 `/data/app.db`，宿主机本地开发请改成仓库绝对路径，例如 `sqlite:////absolute/path/to/StarSorty/data/app.db`。 |
| `API_BASE_URL` | `http://api:4321` | Compose 内部 API 地址，供 scheduler 与服务端渲染中的 Web 使用。 |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:4321` | 浏览器访问 API 的公开地址；该值在 Web 构建时注入，修改后需要重建 Web 镜像。 |

### 批处理与性能

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CLASSIFY_BATCH_SIZE` | `50` | 后台分类默认批次大小。 |
| `CLASSIFY_CONCURRENCY` | `3` | 后台分类默认并发数。 |
| `CLASSIFY_CONCURRENCY_MAX` | `10` | 后台分类并发上限。 |
| `CLASSIFY_BATCH_DELAY_MS` | `0` | 批次间延迟。 |
| `RELEVANCE_CANDIDATE_LIMIT` | `2000` | 相关度重排候选集上限。 |
| `STAR_USER_LOOKUP_CHUNK_SIZE` | `400` | 同步时按用户回填 Star 关系的分批大小。 |
| `REPO_UPSERT_BATCH_SIZE` | `200` | 同步阶段 `repos` 表单批 upsert 大小，减小单次事务锁持有时间。 |
| `TAXONOMY_CACHE_TTL_SECONDS` | `300` | taxonomy 进程内缓存 TTL。 |
| `RULES_CACHE_TTL_SECONDS` | `300` | rules 进程内缓存 TTL。 |
| `SHARED_CACHE_MAX_ENTRIES_PER_NAMESPACE` | `500` | SQLite 共享缓存每个命名空间最多保留的条目数。 |
| `SHARED_CACHE_MAX_BYTES_PER_NAMESPACE` | `5242880` | SQLite 共享缓存每个命名空间最多保留的近似 payload 字节数。 |
| `SHARED_CACHE_CLEANUP_BATCH_SIZE` | `100` | 单次共享缓存过期清理或裁剪的最大批量。 |

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
- 对外部署时，`APP_ENV=production` 与 `ADMIN_TOKEN` 必须同时具备；不要启用 `ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV`。
- 将 `CORS_ORIGINS` 设置为显式域名列表，不要使用 `*`。
- 浏览器管理台现在使用 `HttpOnly` cookie session + `X-CSRF-Token`；部署时优先使用同域反代 `/api`，或至少保持 Web 与 API 处于同站点（same-site）域名下。
- `APP_ENV=production` 时管理员 session cookie 会带 `Secure`；浏览器访问管理台时应使用 HTTPS。
- 如果使用反向代理，保持 `NEXT_PUBLIC_API_BASE_URL` 指向对浏览器可达的公开 API 地址；若采用同域反代，可直接设成 `/api`。
- 保持 `API_BASE_URL` 为容器内可达地址，例如 Compose 默认的 `http://api:4321`。
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
RULE_MIN_THRESHOLD=0.42
RULE_AMBIGUITY_GAP=0.08
```

语义说明：

- `RULE_DIRECT_THRESHOLD` 以上：直接采用规则结果。
- `RULE_AI_THRESHOLD` 到 `RULE_DIRECT_THRESHOLD` 之间：进入 AI 仲裁，并把规则候选作为提示。
- `RULE_MIN_THRESHOLD` 到 `RULE_AI_THRESHOLD` 之间：仍可走 AI，但不再把弱规则当作可靠提示，也不会在 AI 失败后直接回退到弱规则。
- 低于 `RULE_MIN_THRESHOLD`：规则信号视为过弱，只走 AI 或 manual review。
- 当前两名不同分类候选分差小于 `RULE_AMBIGUITY_GAP` 时，会避免直接定类。

### 多用户 Star 聚合

```env
GITHUB_USERNAMES=alice,bob,charlie
GITHUB_MODE=merge
```

### 单机 VPS + 反向代理

```env
APP_ENV=production
ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV=false
CORS_ORIGINS=https://stars.example.com
API_BASE_URL=http://api:4321
NEXT_PUBLIC_API_BASE_URL=/api
```

## 故障排查

- API 启动时提示 `ADMIN_TOKEN is required in production mode`：说明 `APP_ENV=production` 但未配置 `ADMIN_TOKEN`。
- API 启动时提示 `ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV cannot be enabled in production mode`：说明你把本地开发豁免开关错误地带到了生产环境。
- API 启动时提示 `CORS_ORIGINS must be an explicit origin list`：说明生产环境仍使用了通配符或空值。
- 宿主机直接启动 API 时出现 `/data/app.db` 权限错误或 SQLite 无法创建：说明 `DATABASE_URL` 仍指向容器路径，请改成仓库内 `data/app.db` 的绝对路径。
- Web 页面请求错地址：检查 `NEXT_PUBLIC_API_BASE_URL` 是否与部署域名一致；如果刚修改过，记得重建 Web 镜像。
- 动态详情页服务端渲染失败：检查 `API_BASE_URL` 是否仍指向容器内可达的 API 地址。
- scheduler 无法触发同步：检查 `API_BASE_URL`、`SYNC_CRON` 与 `ADMIN_TOKEN` 是否在 scheduler 容器内生效。
- 浏览器管理台登录成功但写操作仍返回 `401`：优先检查 `NEXT_PUBLIC_API_BASE_URL` 是否跨站点、`CORS_ORIGINS` 是否允许当前来源、浏览器是否带上 `starsorty_admin_session` / `starsorty_admin_csrf` cookie，以及 production 环境下是否确实通过 HTTPS 访问。
