# API 接口参考

本文档汇总 StarSorty 当前后端接口，用于快速理解能力边界、鉴权要求和常见调用方式。

## 基本信息

- API 服务默认地址：`http://localhost:4321`
- 在线 OpenAPI 文档：`/docs`
- 健康检查接口：`GET /health`
- 主要返回格式：JSON；导出接口返回 ZIP 文件
- 所有 API 响应都会返回 `X-Request-ID`，可用于关联服务端日志；客户端也可主动传入该请求头复用自己的追踪 ID

## 鉴权约定

- CLI、scheduler 和脚本仍可通过请求头 `X-Admin-Token` 鉴权。
- Web 管理台会先通过 `POST /auth/session` 把 `ADMIN_TOKEN` 交换成 `HttpOnly` session cookie；后续浏览器写操作使用 cookie + `X-CSRF-Token`。
- 当 `ADMIN_TOKEN` 已配置时，未携带或错误的凭证、过期 session 或缺失 CSRF 的写请求会收到 `401`。
- 当 `ADMIN_TOKEN` 未配置时，管理员接口默认返回 `503`，不会再默默开放。
- 仅当显式设置 `ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV=1` 且当前不是 production 环境时，才允许本地开发豁免。
- 建议无论开发或生产，都始终配置 `ADMIN_TOKEN`。
- 浏览器管理台推荐同域反代 `/api`，或至少保证 Web 与 API 处于 same-site 域名下，以便 cookie session 正常工作。

示例：

```bash
curl -X POST "http://localhost:4321/sync" \
  -H "X-Admin-Token: <ADMIN_TOKEN>"
```

### 浏览器管理员会话示例

如果你想在脚本里模拟浏览器管理员会话，而不是直接使用 `X-Admin-Token`，可以按下面顺序：

```bash
curl -c admin.cookies -X POST "http://localhost:4321/auth/session" \
  -H "Content-Type: application/json" \
  -d '{"password":"<ADMIN_TOKEN>"}'

csrf_token=$(awk '$6 == "starsorty_admin_csrf" {print $7}' admin.cookies)

curl -b admin.cookies -X POST "http://localhost:4321/classify/background" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: ${csrf_token}" \
  -d '{"limit":20,"concurrency":2}'

curl -b admin.cookies -X DELETE "http://localhost:4321/auth/session" \
  -H "X-CSRF-Token: ${csrf_token}"
```

说明：

- `starsorty_admin_session` 是 `HttpOnly` session cookie。
- `starsorty_admin_csrf` 是浏览器或脚本需要回传到 `X-CSRF-Token` 的值。
- 生产环境下 session cookie 会带 `Secure`，浏览器侧应通过 HTTPS 访问。

## 异步任务模型

- `POST /sync`、`POST /classify/background`、`POST /tasks/{task_id}/retry` 都会返回任务 ID。
- 可通过 `GET /tasks/{task_id}` 轮询任务状态。
- 分类任务运行状态还可通过 `GET /classify/status` 查看，返回 `status` 字段区分 `idle`、`queued`、`running`、`finished`、`stopped`、`failed`。
- 当分类仍在执行时，重复触发会收到 `409`。
- 分类运行态和质量指标现在会持久化到 SQLite；`/stats` 直接读取 SQLite 版本化快照，`/repos` 会把缓存值与失效版本都共享到 SQLite，并保留一层进程内热点缓存。

## 接口总览

### 健康与鉴权

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/health` | 否 | 基础健康检查；若携带有效管理员凭证，会额外返回安全基线信息。 |
| `GET` | `/auth/check` | 是 | 校验当前管理员身份是否有效。 |
| `POST` | `/auth/session` | 否 | 使用 `ADMIN_TOKEN` 创建浏览器管理员会话。 |
| `DELETE` | `/auth/session` | 是 | 注销当前浏览器管理员会话。 |

### 同步与任务

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/status` | 否 | 查看最近一次同步结果、时间与消息。 |
| `POST` | `/sync` | 是 | 触发 GitHub Star 同步，返回任务 ID。 |
| `GET` | `/tasks/{task_id}` | 否 | 查询任务状态；任务不存在或已清理时返回 `404`。 |
| `POST` | `/tasks/{task_id}/retry` | 是 | 仅支持重试分类任务。 |

### 分类

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/classify` | 是 | 前台执行分类；`force=true` 时会转为后台任务并返回 `202`。 |
| `POST` | `/classify/background` | 是 | 后台批量分类。 |
| `GET` | `/classify/status` | 否 | 查询后台分类运行状态；优先看 `status`，`running` 仅表示当前是否仍有活跃任务。 |
| `POST` | `/classify/stop` | 是 | 请求停止当前后台分类任务；若当前没有本地活跃任务，返回 `{"stopped": false}`。 |

`GET /classify/status` 重点字段说明：

- `status`：`idle`、`queued`、`running`、`finished`、`stopped`、`failed`
- `running`：当前是否仍有活跃后台分类任务
- `last_error`：失败原因；人工停止时，终态通常为 `status=stopped` 且 `last_error="Stopped by user"`，停止请求刚提交但任务尚未退出时可能短暂显示 `Stop requested by user`
- `task_id`：当前活跃任务 ID；任务结束后请优先使用最初拿到的 `task_id` 继续查询 `GET /tasks/{task_id}`
- 停止请求标志会写入 SQLite，共享于不同 worker；后台分类会在批次边界消费这个停止请求

`POST /classify` 与 `POST /classify/background` 的主要请求体字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `limit` | `int` | `20` | 分类数量；`0` 表示由服务端决定批次或用于全量模式。 |
| `force` | `bool` | `false` | 强制重新分类已有仓库。 |
| `include_readme` | `bool` | `true` | 分类时是否拉取 README 摘要。 |
| `preference_user` | `string` | `global` | 使用哪位用户的偏好映射。 |
| `concurrency` | `int` | `null` | 仅后台分类可用，并发数下限为 `1`。 |
| `cursor_full_name` | `string` | `null` | 仅后台分类重试续跑时使用。 |

### 仓库检索与人工修正

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/repos` | 否 | 多条件检索仓库列表。 |
| `GET` | `/repos/failed` | 是 | 查看分类失败次数较高的仓库。 |
| `POST` | `/repos/failed/reset` | 是 | 清空失败计数。 |
| `GET` | `/repos/review/low-confidence` | 是 | 查看低置信度、规则回退、需要人工复核的分类队列。 |
| `GET` | `/repos/{full_name}` | 否 | 查看单仓库详情。 |
| `PATCH` | `/repos/{full_name}/override` | 是 | 覆盖分类结果、标签或备注。 |
| `GET` | `/repos/{full_name}/overrides` | 否 | 查看人工修改历史。 |
| `POST` | `/repos/{full_name}/readme` | 是 | 重新抓取并保存 README 摘要。 |

`GET /repos` 主要查询参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `q` | `string` | - | 关键词检索。 |
| `language` | `string` | - | 语言过滤。 |
| `min_stars` | `int` | - | 最少 star 数。 |
| `category` | `string` | - | 一级分类过滤。 |
| `subcategory` | `string` | - | 二级分类过滤。 |
| `tag` | `string` | - | 单标签过滤。 |
| `tags` | `string` | - | 多标签，逗号分隔。 |
| `tag_mode` | `and \| or` | `or` | 多标签交集或并集。 |
| `sort` | `relevance \| stars \| updated` | `stars` | 排序方式。 |
| `user_id` | `string` | `global` | 关联个性化画像与偏好。 |
| `star_user` | `string` | - | 按某个 GitHub 用户的 Star 来源过滤。 |
| `limit` | `int` | `50` | 分页大小。 |
| `offset` | `int` | `0` | 偏移量。 |

`GET /repos` 响应补充字段：

- `total`：真实命中总数，用于统计与反馈，不再受相关度候选集上限截断。
- `has_more`：当前排序与分页条件下是否还可继续请求下一页。
- `next_offset`：继续翻页时建议使用的下一个 offset；若无下一页则为 `null`。
- `pagination_limited`：当 `sort=relevance` 且候选集被 `RELEVANCE_CANDIDATE_LIMIT` 截断时为 `true`。

`PATCH /repos/{full_name}/override` 支持的请求体字段：

- `category`
- `subcategory`
- `tags`
- `tag_ids`
- `note`

人工覆盖成功后，服务端会写入覆盖历史与训练样本，并把可推断的标签/分类映射沉淀到 `global` 偏好中，供后续分类使用。

`GET /repos/review/low-confidence` 支持的查询参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `confidence_threshold` | `float` | `0.62` | 低于该置信度的仓库进入复核队列。 |
| `limit` | `int` | `30` | 返回数量，上限 `200`。 |

响应项包含 `repo` 与 `review_reason`。`repo` 复用 `RepoOut`，因此可展示 `ai_confidence`、`ai_reason`、`ai_rule_candidates`、`readme_summary` 等证据字段。

### 分类体系、统计与配置

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/taxonomy` | 否 | 获取分类、子类和标签定义。 |
| `GET` | `/stats` | 否 | 获取统计面板数据。 |
| `GET` | `/metrics/quality` | 否 | 获取检索、分类与 SQLite 锁重试指标。 |
| `GET` | `/metrics/consistency` | 是 | 获取一致性巡检报告。 |
| `GET` | `/api/config/client-settings` | 否 | 前端公开配置，只返回安全字段。 |
| `GET` | `/settings` | 是 | 读取管理员可见运行配置与 token 配置状态。 |
| `PATCH` | `/settings` | 是 | 修改可持久化的非敏感运行配置。 |

`GET /stats` 支持的查询参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `refresh` | `bool` | `false` | 强制绕过缓存重新计算。 |
| `snapshot` | `bool` | `true` | 是否优先使用版本化快照。 |

说明：

- `/stats` 现在直接依赖 SQLite 中的 `repo_stats_version + stats_snapshots`
- 当写路径提升 `repo_stats_version` 后，下次请求会自动重算并刷新快照

`GET /metrics/quality` 当前包含的重点字段：

- `classification_total`、`rule_hit_total`、`ai_fallback_total`、`empty_tag_total`、`uncategorized_total`
- `search_total`、`search_zero_result_total`
- `api_request_total`、`api_error_total`、`api_request_latency_ms_total`、`api_request_latency_ms_avg`
- `task_queued_total`、`task_finished_total`、`task_failed_total`、`task_stopped_total`、`task_failure_rate`
- `cache_hit_total`、`cache_miss_total`、`cache_hit_rate`
- `db_lock_conflict_total`：捕获到 SQLite 锁冲突的次数
- `db_lock_retry_total`：进入退避重试的次数
- `db_lock_retry_exhausted_total`：达到最大重试次数后仍失败的次数

说明：

- 上述质量指标现在持久化在 SQLite 中，可跨 worker 读取同一份累计值

`PATCH /settings` 可更新的字段：

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

### 个性化与训练数据

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/preferences/{user_id}` | 是 | 获取用户偏好映射。 |
| `PATCH` | `/preferences/{user_id}` | 是 | 更新用户偏好映射与规则优先级。 |
| `POST` | `/feedback/search` | 否 | 记录搜索反馈。 |
| `POST` | `/feedback/click` | 否 | 记录点击反馈。 |
| `GET` | `/interest/{user_id}` | 是 | 查看用户兴趣画像。 |
| `GET` | `/training/samples` | 是 | 导出训练样本。 |
| `GET` | `/training/fewshot` | 是 | 导出 few-shot 样本。 |

说明：

- 公开页面如需读取安全可公开的前端配置，请使用 `GET /api/config/client-settings`。
- `GET /settings`、`GET /preferences/{user_id}`、`GET /interest/{user_id}`、`GET /repos/failed` 现均要求管理员 token。

偏好接口请求体字段：

- `tag_mapping`：标签映射，例如把内部标签重定向到更贴近个人习惯的标签。
- `rule_priority`：规则优先级权重，用于调整规则排序。

反馈接口请求体字段：

- `POST /feedback/search`：`query`、`results_count`、`selected_tags`、`category`、`subcategory`
- `POST /feedback/click`：`full_name`、`query`

说明：

- 公开反馈接口仍兼容接收 `user_id` 字段，但服务端会忽略该值，不会据此写入 `global` 或任意用户兴趣画像。

### 导出

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/export/obsidian` | 是 | 以流式响应导出 Obsidian ZIP 包。 |

支持的查询参数：

- `tags`：逗号分隔的标签过滤器
- `language`：按语言过滤导出内容

说明：

- 服务端会边生成边输出 ZIP，不再等待整个归档先在内存中组装完成

## 常见调用示例

### 触发后台分类

```bash
curl -X POST "http://localhost:4321/classify/background" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: <ADMIN_TOKEN>" \
  -d '{"limit":50,"concurrency":3,"include_readme":true}'
```

### 查询相关度排序结果

```bash
curl "http://localhost:4321/repos?q=vector%20database&sort=relevance&tags=rag,embedding&tag_mode=or&limit=20"
```

### 更新单仓库人工覆盖

```bash
curl -X PATCH "http://localhost:4321/repos/openai/openai-python/override" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: <ADMIN_TOKEN>" \
  -d '{"category":"AI","subcategory":"SDK","tag_ids":["ai.llm","dev.sdk"],"note":"手动修正"}'
```

## 约定与注意事项

- `/docs` 仍然是请求/响应结构的最终权威来源。
- 当前 API 应用版本为 `0.2.0`（2026-03-07）。
- StarSorty 当前没有显式版本化 API 前缀，升级时请关注变更说明。
- 管理员接口普遍带有更严格的速率限制。
- 大批量任务建议优先使用后台接口并配合任务轮询。
- 浏览器端管理员登录已切换为 cookie session；`X-Admin-Token` 更适合 CLI、scheduler 与运维脚本。
