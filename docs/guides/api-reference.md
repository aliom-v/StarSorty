# API 接口参考

本文档汇总 StarSorty 当前后端接口，用于快速理解能力边界、鉴权要求和常见调用方式。

## 基本信息

- API 服务默认地址：`http://localhost:4321`
- 在线 OpenAPI 文档：`/docs`
- 健康检查接口：`GET /health`
- 主要返回格式：JSON；导出接口返回 ZIP 文件

## 鉴权约定

- 写操作与管理员接口通过请求头 `X-Admin-Token` 鉴权。
- 当 `ADMIN_TOKEN` 已配置时，未携带或错误的 token 会收到 `401`。
- 当 `ADMIN_TOKEN` 未配置时，开发环境中的管理员接口不会被保护；生产环境禁止这种配置。
- 建议无论开发或生产，都始终配置 `ADMIN_TOKEN`。

示例：

```bash
curl -X POST "http://localhost:4321/sync" \
  -H "X-Admin-Token: <ADMIN_TOKEN>"
```

## 异步任务模型

- `POST /sync`、`POST /classify/background`、`POST /tasks/{task_id}/retry` 都会返回任务 ID。
- 可通过 `GET /tasks/{task_id}` 轮询任务状态。
- 分类任务运行状态还可通过 `GET /classify/status` 查看。
- 当分类仍在执行时，重复触发会收到 `409`。

## 接口总览

### 健康与鉴权

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/health` | 否 | 基础健康检查；若携带有效管理员 token，会额外返回安全基线信息。 |
| `GET` | `/auth/check` | 是 | 验证管理员 token 是否有效。 |

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
| `GET` | `/classify/status` | 否 | 查询后台分类运行状态。 |
| `POST` | `/classify/stop` | 是 | 请求停止当前后台分类任务。 |

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

`GET /metrics/quality` 当前包含的重点字段：

- `classification_total`、`rule_hit_total`、`ai_fallback_total`、`empty_tag_total`、`uncategorized_total`
- `search_total`、`search_zero_result_total`
- `db_lock_conflict_total`：捕获到 SQLite 锁冲突的次数
- `db_lock_retry_total`：进入退避重试的次数
- `db_lock_retry_exhausted_total`：达到最大重试次数后仍失败的次数

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
| `GET` | `/export/obsidian` | 是 | 导出 Obsidian ZIP 包。 |

支持的查询参数：

- `tags`：逗号分隔的标签过滤器
- `language`：按语言过滤导出内容

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

## 相关阅读

- `docs/README.md`
- `docs/guides/project-structure.md`
- `docs/guides/configuration.md`
- `docs/guides/deployment-operations.md`
