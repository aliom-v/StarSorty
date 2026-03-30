# 运行态与缓存一致性

更新时间：`2026-03-28`

本文档说明 StarSorty 当前哪些运行态已经通过 SQLite 共享，哪些仍然只是进程内优化，以及这对单机多 worker 部署意味着什么。

## 目标

当前实现不是把所有状态都做成完整分布式系统，而是先把最容易分裂、最容易误判的运行态收敛到单一来源。

设计原则只有两条：

- 能直接落到 SQLite 且读写成本可接受的状态，优先共享
- 只为降低热点查询成本而存在的短生命周期缓存，允许保留进程内实现，但要避免旧数据长期分裂

## 当前已经共享的状态

### 1. 后台分类运行态

对应实现：

- `api/app/state.py`
- `api/app/runtime_store.py`
- `api/app/routes/classify.py`

当前行为：

- `classification_state` 会持久化到 SQLite `runtime_state`
- 停止请求标志也会持久化
- `/classify/status` 读取的是共享运行态，不再只看当前进程内存

### 2. 质量指标

对应实现：

- `api/app/state.py`
- `api/app/runtime_store.py`
- `api/app/routes/stats.py`

当前行为：

- 指标累计值持久化到 SQLite `runtime_metrics`
- `/metrics/quality` 返回的是共享累计值

### 3. `/stats` 聚合结果

对应实现：

- `api/app/db/stats.py`
- `api/app/routes/stats.py`

当前行为：

- `/stats` 直接依赖 SQLite 中的 `repo_stats_version + stats_snapshots`
- repo/classification/override 相关写路径会提升 `repo_stats_version`
- 版本未变化时，`get_repo_stats()` 直接复用 SQLite 快照

这意味着：

- `/stats` 的一致性来源是 SQLite 快照，而不是各 worker 的内存缓存
- 不需要再叠一层路由级 `SimpleCache`

### 4. `/repos` 缓存失效

对应实现：

- `api/app/cache.py`
- `api/app/cache_store.py`
- `api/app/routes/repos.py`
- `api/app/routes/classify.py`
- `api/app/routes/sync.py`

当前行为：

- `/repos` 查询结果会同时写入当前进程内存与 SQLite `cache_entries`
- `repos` 命名空间的失效版本仍会写入 SQLite `app_settings`
- 任一 worker 执行 `invalidate_prefix("repos")` 后，其他 worker 的旧缓存会在下次读取时自动判旧失效
- 冷 worker 在本地 miss 时，可以直接复用 SQLite 中已有的 `/repos` 缓存值

这意味着：

- `/repos` 的旧数据不会因为 worker 切换而长期残留
- 不同 worker 之间可以复用同一份 SQLite 缓存值
- 当前进程仍会保留一层本地热点缓存，避免每次命中都反序列化共享 payload

## 当前仍然是进程内的状态

### 1. `/repos` 缓存值本体

- `/repos` 虽然已经共享缓存值，但当前仍是“SQLite 共享缓存 + 本地热副本”模型
- 它解决的是单机多 worker 一致性与复用，不等于完整独立缓存服务

### 2. taxonomy / rules 缓存

对应实现：

- `api/app/taxonomy.py`
- `api/app/rules.py`

当前行为：

- 仍是进程内 TTL + 文件变更检测
- 更适合单机、自托管、少量 worker 的运行方式

### 3. 本地任务对象与锁

对应实现：

- `api/app/state.py`

当前行为：

- 例如 `classification_task`、`classification_lock`、本地 `asyncio.Event`
- 这些对象只在当前进程有效
- 当前方案是“共享运行态 + 本地执行控制”，不是跨进程任务调度系统

## 当前应该怎么理解这个系统

可以把 StarSorty 现在的状态模型看成三层：

1. SQLite 共享真相层：运行态、质量指标、repo stats 快照、cache invalidation version
2. 进程内加速层：`/repos` 本地热点缓存、taxonomy/rules 解析缓存
3. 本地执行层：后台任务对象、锁、事件与当前 worker 内协程调度

在这个边界下，当前最合适的部署模型仍然是：

- 单机
- SQLite
- 单实例或少量 worker

它已经比“所有状态都在内存里”稳很多，但还没有到“完整横向扩展缓存/任务系统”的程度。

## 多 worker 下应当预期的行为

- `/classify/status` 与 `/metrics/quality` 应该读到同一份共享状态
- `/stats` 应该复用同一份 SQLite 快照结果
- `/repos` 在写入后不会长期保留旧缓存，其他 worker 也可以直接复用 SQLite 中已有缓存值

如果仍看到明显分裂，优先排查：

1. `DATABASE_URL` 是否确实指向同一份 SQLite 文件
2. 是否仍有旧 worker 未重启
3. 是否误把“缓存重新预热”当成“旧缓存没有失效”

## 后续还值得继续做什么

当前还值得继续推进的只有两类工作：

1. 为 `/repos` 共享缓存补充尺寸治理、过期清理和热点观测
2. 如果后续访问量继续上升，再评估是否把 SQLite 共享缓存迁移到专门的缓存服务
