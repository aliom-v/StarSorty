# 当前工程审计

更新时间：`2026-03-28`

本文档用于记录 StarSorty 当前已经确认的工程问题、运行边界和后续改造建议。后续继续做安全、可靠性或架构演进时，优先以本页和 `../roadmap/current-priorities.md` 为准；需要展开成当前阶段的具体执行方案时，再看 `../roadmap/optimization-execution-plan.md`。

## 已验证基线

- 架构仍为 `FastAPI + SQLite + Next.js + APScheduler`
- 默认部署模型仍是 `docker-compose.yml` 中的单机单实例编排
- 本地验证已通过：
  - `npm run docs:check`
  - `npm run scripts:test`
  - `npm run api:test`
  - `npm run web:test`
  - `npm run web:lint`
  - `npm run web:build`
  - `npm run web:smoke`

## 近期已收口

### 1. 管理鉴权已改成默认拒绝

- 未配置 `ADMIN_TOKEN` 时，管理员接口现在默认返回 `503`
- 只有显式设置 `ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV=1` 且非 production 环境时，才允许本地开发豁免
- scheduler 也会在缺少管理员鉴权时停止触发 `/sync`，避免定时任务持续打无效请求

### 2. Web 管理台已切到服务端会话

- 浏览器不再把原始管理员口令保存到 `localStorage` / `sessionStorage`
- 登录流程改为 `ADMIN_TOKEN -> HttpOnly session cookie`
- 浏览器写操作需要携带 session cookie 与 `X-CSRF-Token`

### 3. 配置热路径已改成快照缓存 + 显式失效

- `get_settings()` 现在会缓存当前进程内的配置快照
- `PATCH /settings` 写入 SQLite 覆盖项后，会触发当前进程配置快照失效
- 环境变量发生变化时，也会自动重建配置快照

### 4. 后台分类停止语义已收口

- `GET /classify/status` 现在显式返回 `status`
- `POST /classify/stop` 只会在当前进程确实有活跃分类任务时返回 `{"stopped": true}`
- 后台分类任务落库终态已区分 `finished`、`stopped`、`failed`

### 5. Obsidian 导出已改成真正流式输出

- `/export/obsidian` 现在使用 `StreamingResponse`
- ZIP 内容按条目增量写出，不再先把整个归档放进单个 `BytesIO`
- 单次导出的内存占用不再跟最终 ZIP 文件体积线性绑定

### 6. 分类运行态与质量指标已落到 SQLite

- `classification_state` 现在会同步持久化到 SQLite
- `/classify/stop` 会同时写入共享停止请求标志，后台循环会在批次边界读取
- `/metrics/quality` 改为读取 SQLite 中累计的共享指标，不再完全依赖当前进程内存

### 7. 运行态与缓存一致性已进一步收口

- `/stats` 现在直接依赖 SQLite 版本化快照，不再叠加一层路由级内存缓存
- `/repos` 现在会把缓存值写入 SQLite，同时保留本地热点缓存
- `repos` 命名空间的失效版本仍会写入 SQLite，任一 worker 执行 `invalidate_prefix("repos")` 后，其他 worker 的旧缓存会在下次读取时自动判旧失效

## 当前已确认问题

### 1. 当前缓存仍然是单机 SQLite 方案，不是独立缓存服务

- `/stats` 与 `/repos` 现在都能通过 SQLite 跨 worker 复用
- 但 `/repos` 仍是“SQLite 共享缓存 + 本地热点缓存”的单机实现
- 当前还没有独立缓存服务、跨节点一致性和专门的缓存淘汰治理

影响：

- 当前模型仍然更适合单机单实例
- 多 worker 下 `/stats` 与 `/repos` 都不会长期分裂
- 如果继续走多实例扩展，下一步仍要决定是否引入真正的共享缓存层

### 2. 开发与测试运行时依赖仍然偏脆弱

- API 测试当前只接受 Python `3.11` - `3.13` 本地运行时，`3.14+` 会被直接拦截
- 不满足条件时，需要 Docker fallback
- Web 测试和 smoke 依赖本地 IPC socket 与端口绑定能力

影响：

- 新环境接手项目时，先解决运行时边界，再开始改代码
- 当前仓库已经有脚本兜底，但开发体验仍明显依赖本地环境质量

## 当前结论

### 可以认为已经稳定的部分

- 基础测试门禁已补齐
- 前端构建和 smoke 路径可跑通
- 单机自托管链路可用
- `/stats` 已收敛到 SQLite 快照，`/repos` 也已能跨 worker 共享缓存值

### 不能高估的部分

- 管理鉴权的默认边界已经收口，但浏览器管理员会话目前仍依赖 same-site cookie 部署约束
- 当前运行模型虽然把分类运行态、质量指标、`/stats` 快照和 `/repos` 共享缓存都落到了 SQLite，但仍未准备好面向多节点扩展
- CLI / scheduler 仍然使用共享 header 密钥模型

## 建议的改造顺序

1. 先把 same-site 部署约束和当前管理员会话边界固化到部署模板与运维检查项
2. 再决定是否需要把 `/repos` 从 SQLite 共享缓存继续推进到独立缓存服务
3. 最后统一开发运行时基线，减少 Python / Docker / IPC 差异
