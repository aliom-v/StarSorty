# StarSorty 全面优化实施总方案（2026-03）

## 1. 文档目的与范围

本方案用于统一 StarSorty 后续优化方向，覆盖：

1. 后端性能与可靠性
2. 前端体验与可维护性
3. 安全与访问控制
4. 数据层与检索质量
5. 测试、CI/CD、运维与发布

目标不是“功能堆叠”，而是建立一条可持续迭代的工程化路径，让系统在数据规模增长时仍可稳定运行。

---

## 2. 当前基线（截至 2026-03-05）

### 2.1 系统基线

- 架构：`FastAPI + SQLite + Next.js + APScheduler`
- 核心链路：`sync -> classify -> repos/search -> export`
- 已完成项：语义检索 Phase 1/2、任务重试、质量指标基础埋点

### 2.2 工程基线

- `web` lint 可通过
- `api` 当前无自动化测试用例执行
- `web` 生产构建存在 webpack 报错（需优先修复并纳入门禁）

### 2.3 风险基线

- 生产模式默认安全已收敛（`APP_ENV=production` 下未配置 `ADMIN_TOKEN` 将拒绝启动）
- 生产模式 CORS 已收敛（拒绝 `CORS_ORIGINS=*` 或空值）
- 开发模式仍允许无 `ADMIN_TOKEN` 运行（用于本地调试），需避免误用于对外部署
- 搜索相关性排序在大数据量下存在全量拉取后内存重排问题
- 同步链路在大账号下存在 SQL 参数数量与批量写入压力风险

### 2.4 执行进展（更新于 2026-03-07）

- 已落地（Phase 1 / P1）：
  - 搜索重排候选集优化：`/repos sort=relevance` 增加 `RELEVANCE_CANDIDATE_LIMIT`，改为候选集限流后重排
  - 同步链路参数上限修复：`_load_star_users` 改为分批 `IN` 查询，增加 `STAR_USER_LOOKUP_CHUNK_SIZE`
- 已落地（Phase 1 / P1，继续）：
  - taxonomy 缓存化：`load_taxonomy` 增加 `TAXONOMY_CACHE_TTL_SECONDS` + 文件 `mtime` 感知
  - rules 缓存化：`load_rules` 增加 `RULES_CACHE_TTL_SECONDS` + 文件 `mtime` 感知
- 已落地（质量保障）：
  - 新增回归测试 `api/tests/test_phase1_optimizations.py`
  - 覆盖：`RELEVANCE_CANDIDATE_LIMIT`、`_load_star_users` 分批查询、taxonomy/rules 缓存热更新
  - 在 API Docker 环境验证通过（4 passed）
- 已落地（CI 门禁）：
  - 新增 `.github/workflows/ci.yml`
  - 覆盖 `api-tests`（pytest）与 `web-quality`（lint + build）
- 已落地（Phase 0 / P0）：
  - 生产环境安全基线：`APP_ENV=production` 且未配置 `ADMIN_TOKEN` 时，API 启动阶段拒绝运行
  - 导出接口鉴权：`/export/obsidian` 增加管理员鉴权
  - 健康检查内部安全字段：`/health` 在管理员请求下返回 `security` 自检信息
  - CORS 边界收敛：生产环境拒绝 `CORS_ORIGINS=*` 或空值，禁止宽松来源上线
- 已落地（安全回归）：
  - 新增 `api/tests/test_security_baseline.py`
  - 覆盖生产模式 token 强制校验、导出鉴权、`/health` 内部字段可见性、CORS 生产校验
  - 在 Docker Python 3.11 环境执行 `api/tests`，共 14 passed
- 已落地（Phase 3 / P2）：
  - `/stats` 增加版本化快照复用，repo 数据未变化时优先返回同版本快照
  - repo/classification/override 写路径自动提升 `repo_stats_version`
  - 支持 `/stats?snapshot=false` 强制走实时聚合
  - 新增 `/metrics/consistency` 管理员巡检接口，覆盖 FTS 漂移、分类异常、标签字段规范化检查
- 已补充（Phase 1 / P1，待执行量化）：
  - 新增 `evaluation/benchmark_api_perf.py`，覆盖 5k 检索与大账号同步离线压测场景
  - 支持通过 `npm run api:bench` 输出压测报告 `evaluation/benchmarks/latest-report.json`
- 待继续（Phase 1）：
  - 基于 5k 数据集做检索 P95 与大账号同步压测，补充量化结果
- 当前建议默认配置：
  - `RELEVANCE_CANDIDATE_LIMIT=2000`
  - `STAR_USER_LOOKUP_CHUNK_SIZE=400`
  - `REPO_UPSERT_BATCH_SIZE=200`
  - `TAXONOMY_CACHE_TTL_SECONDS=300`
  - `RULES_CACHE_TTL_SECONDS=300`

### 2.5 检查补充与本轮执行（更新于 2026-03-08）

- 已落地（P0 / security）：
  - 公开反馈接口 `POST /feedback/search`、`POST /feedback/click` 不再接受客户端传入的 `user_id` 污染 `global` 或任意用户画像。
  - 匿名反馈仅保留事件记录，不再直接更新 `user_interest_profiles`。
- 已落地（P1 / backend perf）：
  - FTS 初始化从“启动即 drop/recreate”改为“仅在对象缺失或 schema 漂移时重建”，避免每次启动重建全文索引。
  - `/repos` 仅在 `sort=relevance` 且存在查询词时才加载兴趣画像，去除 `stars/updated` 路径上的无效 DB 读。
  - 补齐 `subcategory` 与 `updated_at + stargazers_count + full_name` 索引，覆盖 `/repos` 常见排序与筛选路径。
  - `category/subcategory` 查询条件从 `COALESCE(NULLIF(...), ...)` 改为可被普通索引更好利用的显式条件分支。
  - `upsert_repos` 改为按 `REPO_UPSERT_BATCH_SIZE` 分批写入与提交，缩短大账号同步时的单事务锁持有时间。
- 已落地（P1 / classify）：
  - 分类批处理主链路接入 `classify_repos_with_retry` 批量 AI 请求；当批量结果缺失或批量调用失败时，按 repo 回退到单次 AI / 规则兜底。
- 已落地（P1 / reliability）：
  - `/tasks/{task_id}` 对缺失任务返回 `404`，与前端轮询恢复逻辑对齐。
- 已落地（P1 / search contract）：
  - `relevance` 排序的 `total` 恢复为真实命中总数，分页继续能力改由 `has_more/next_offset` 明确返回。
  - 前端首页“加载更多”改为消费服务端分页字段，不再用 `total` 猜测是否还有下一页。
- 已落地（P1 / observability）：
  - `_retry_on_lock()` 统一累计 SQLite 锁冲突、重试与重试耗尽计数，并通过 `/metrics/quality` 暴露。
- 已补充（回归测试）：
  - 新增覆盖：匿名反馈收口、非 relevance 查询跳过兴趣画像、缺失任务返回 `404`、FTS 二次初始化不丢索引数据、分类批量 AI 热路径、relevance 分页契约、SQLite 锁重试指标。
- 已落地（P1 / frontend regression）：
  - 新增无依赖前端逻辑回归测试，覆盖首页分页状态合并、任务轮询失败/404 恢复判定，以及共享 request tracker 的并发请求保护。
  - 首页与 repo 详情页改为复用共享请求保护逻辑，旧请求返回不再覆盖较新的页面状态。
- 已落地（P2 / frontend polling）：
  - 首页任务轮询从固定 `setInterval` 改为单次调度，避免请求慢时叠加并发轮询。
  - 轮询失败时按指数退避延长下一次请求间隔，恢复后自动回到基础轮询间隔。
- 已落地（P2 / frontend maintainability）：
  - `web/app/page.tsx` 拆分为布局页、首页数据控制 hook 与结果列表组件，首页状态、请求与视图分层更清晰。
  - 首页共享类型迁移到独立模块，减少页面文件内联类型与请求编排耦合。
  - 首页主文件从约 `1045` 行收缩到 `153` 行，同时保留现有分页、请求竞态保护与任务轮询行为。
- 已落地（P2 / observability）：
  - API middleware 统一生成/透传 `X-Request-ID`，所有 `starsorty.*` 日志默认带上 `request_id/task_id` 上下文。
  - 后台同步与后台分类任务创建时继承请求上下文，并在任务注册、状态更新、异常日志中关联 `task_id`。
  - `/metrics/quality` 补充 API 请求、错误、延迟、任务吞吐与缓存命中指标，用于更快定位慢请求与后台任务异常。
- 已补充（P2 / observability follow-up）：
  - 新增可观测性回归测试，覆盖 request id 透传/生成、API 错误计数、任务指标累计与派生质量指标计算。
  - `docs/guides/deployment-operations.md` 增加故障定位手册，覆盖同步失败、分类失败、SQLite 锁冲突与 Web 构建失败排查链路。

---

## 3. 北极星目标与量化指标

## 3.1 产品目标

1. 检索“找得到且找得准”
2. 分类稳定且可解释
3. 同步与任务执行可观测、可恢复
4. 默认安全可上线

## 3.2 工程指标（季度目标）

| 维度 | 当前状态 | 目标值 |
| --- | --- | --- |
| `/repos` 检索 P95（5k 仓库） | 未稳定量化 | <= 800ms |
| 背景分类失败率 | 已有统计 | <= 2% |
| 搜索零结果率 | 已有统计 | 下降 20%+ |
| 构建成功率（主干） | 不稳定 | 100% |
| 自动化测试覆盖（API 核心路径） | 基本缺失 | >= 60% lines（核心模块） |
| 关键变更回滚时长 | 无标准 | <= 10 分钟 |
| 安全基线（管理写接口） | 可误开放 | 默认强制鉴权 |

---

## 4. 优先级与执行原则

## 4.1 优先级定义

- `P0`：安全/数据一致性/可用性阻断问题
- `P1`：核心体验与性能瓶颈
- `P2`：可维护性与工程效率
- `P3`：长期能力建设与体验增强

## 4.2 执行原则

1. 小步快跑，每周可发布
2. 每项改造必须有“指标 + 验收 + 回滚”
3. 优先增量兼容，避免一次性重写
4. 功能开关保护高风险变更

---

## 5. 分域优化清单（完整）

## 5.1 安全与访问控制（P0）

1. `ADMIN_TOKEN` 强制化策略
   - 生产模式下未配置则拒绝启动，禁止“默认放行”
   - 增加启动时安全自检日志与 `/health` 扩展字段（仅内部可见）
2. 管理写接口统一鉴权审计
   - 覆盖：`/sync`、`/classify*`、`/settings`、`/repos/*/override`、`/export/*`
   - 导出接口加管理员鉴权与速率限制分级
3. CORS 与部署边界收敛
   - 禁止生产使用 `*` + 凭证组合
   - 文档明确反向代理与内网部署建议
4. 密钥治理
   - UI 侧不持久化长期高权限密钥
   - 日志脱敏策略统一（已具备基础能力，补充回归测试）
5. 公开反馈与画像隔离
   - 匿名反馈不得写入 `global` 或任意用户画像
   - 个性化排序仅允许绑定到受控的用户或会话标识

验收：

- 未配置 `ADMIN_TOKEN` 时生产启动失败
- 所有写操作接口鉴权覆盖率 100%
- 安全回归用例覆盖关键路径

## 5.2 后端性能与扩展（P1）

1. 搜索重排内存优化
   - 避免 `relevance` 模式全量拉取；改为“候选集上限 + 分页稳定重排”
   - 增加 `RELEVANCE_CANDIDATE_LIMIT` 配置
2. 同步链路批处理化
   - GitHub 拉取后分批 upsert，降低事务时间和内存峰值
   - `_load_star_users` 改分批 `IN` 查询，规避 SQLite 变量上限
3. 配置与规则加载缓存
   - taxonomy/rules 增加进程内缓存与热更新策略（TTL 或文件变更时间）
4. 任务并发与锁等待优化
   - 增加 DB 锁冲突指标、重试次数指标
   - 对高写路径评估更细粒度事务边界
5. 启动阶段降载
   - 避免每次启动重建 FTS / 大型派生索引
   - 仅在对象缺失或 schema 漂移时执行 rebuild

验收：

- 5k 数据集检索 P95 达标
- 同步大账号场景无 SQL 参数上限报错
- 任务高峰期锁重试次数下降

## 5.3 数据层与索引（P1）

1. 索引审视与补齐
   - 覆盖常见筛选：`category/subcategory/language/stars/updated_at`
   - 对 JSON 字段检索路径评估映射表替代方案（中期）
   - 避免查询条件使用难以命中索引的 `COALESCE(NULLIF(...), ...)` 热路径写法
2. 统计查询降载
   - `stats` 已支持版本化快照复用，避免频繁全表聚合
   - 保留 `/stats?snapshot=false` 作为实时聚合兜底路径
3. 数据一致性检查任务
   - 已支持通过 `/metrics/consistency` 校验 FTS 行数与主表一致性
   - 已支持校验分类字段、标签字段（JSON / tag_ids）规范化状态

验收：

- 慢查询占比下降
- 统计接口在高频访问下稳定

## 5.4 分类与检索质量（P1/P2）

1. 分类链路精度治理
   - 规则候选评分与 AI 仲裁继续优化（阈值可配置）
   - 引入“人工覆盖反馈回放”验证链路
   - 批量分类默认优先走 batch AI，请求失败时再回退到单 repo 调用或规则兜底
2. 检索解释能力增强
   - 统一 `match_reasons` 字典与前端文案
   - 提供调试模式输出得分拆解（仅管理员）
3. 质量评测体系
   - 固化 `golden_set` 回放脚本
   - 每次规则/排序改动必须跑离线评测并输出 diff

验收：

- 分类准确率与搜索命中率有可追踪提升
- 每次策略更新可给出前后对比报告

## 5.5 前端体验与可维护性（P2）

1. 大文件拆分
   - `web/app/page.tsx` 组件化拆分：状态、数据请求、视图分层
   - 降低单文件复杂度，提升可测试性
2. 数据请求层统一
   - 抽离 API 客户端、错误处理、重试策略
   - 统一请求取消与并发竞争处理模式
3. 任务轮询体验优化
   - 增加指数退避与可恢复机制
   - 更明确的状态机（queued/running/failed/finished）
4. 构建稳定性治理
   - 定位并修复 `next build` webpack 报错
   - 把 `build + lint` 纳入 CI 强门禁

验收：

- 主页主文件体积显著下降
- `web` 构建稳定通过
- 轮询失败恢复体验可复现验证

## 5.6 可靠性与可观测性（P2）

1. 指标体系完善
   - API 延迟、错误率、DB 锁冲突、任务吞吐、缓存命中率
2. 结构化日志标准化
   - 全链路关联 `task_id/request_id`
3. 运行手册
   - 增加故障定位手册（同步失败、分类失败、锁冲突、构建失败）

验收：

- 主要故障 10 分钟内可定位
- 任务异常具备可追踪上下文

## 5.7 测试与质量门禁（P0/P1）

1. API 核心用例补齐
   - `sync/classify/repos/settings/tasks` 路由层
   - `db/search/classification` 核心数据逻辑
2. 回归用例
   - 管理鉴权、安全路径、任务重试与中断恢复
   - 覆盖 `relevance` 分页契约、任务过期恢复、前端轮询与并发请求路径
3. CI 门禁
   - `pytest + web lint + web build`
   - 合并前必须绿灯

验收：

- 核心路径测试覆盖达标
- 主干分支无“无测试发布”

## 5.8 发布与回滚体系（P2）

1. 功能开关矩阵
   - 分类、搜索、缓存、重排等策略均可快速开关
2. 发布节奏
   - 每周一次小版本，包含变更摘要与风险说明
3. 回滚预案
   - 数据层变更必须有回滚脚本与兼容窗口

验收：

- 单项策略可快速禁用
- 生产异常可在 10 分钟内切回稳定路径

---

## 6. 分阶段实施路线（12 周）

## Phase 0（第 1-2 周，P0）

1. 强制管理鉴权与导出鉴权
2. 修复 `web` 构建失败并接入 CI 门禁
3. 建立最小测试骨架（API smoke + 关键路由）

里程碑：

- 可安全发布
- 构建与最小回归可自动执行

## Phase 1（第 3-5 周，P1）

1. 搜索重排候选集优化（已完成：`RELEVANCE_CANDIDATE_LIMIT`）
2. 同步链路分批写入与 SQL 参数上限修复（部分完成：`_load_star_users` 分批查询）
3. taxonomy/rules 缓存化（已完成：TTL + mtime 热更新）

里程碑：

- 核心接口性能显著改善
- 大账号同步稳定

## Phase 2（第 6-8 周，P1/P2）

1. 分类质量回放流程
2. 指标与日志标准化
3. 前端主页拆分重构（不改业务行为）

里程碑：

- 质量变化可量化
- 前端复杂度下降

## Phase 3（第 9-10 周，P2）

1. 统计降载与数据一致性巡检任务
2. 运行手册与故障处置流程

里程碑：

- 运维响应更快
- 异常定位链路完善

## Phase 4（第 11-12 周，P3）

1. 个性化检索权重优化
2. 长期演进项（如外部缓存、多实例支持）技术预研

里程碑：

- 可持续扩展方案明确

---

## 7. 任务拆分模板（每项改造都使用）

每个优化任务必须包含：

1. 变更背景
2. 影响范围（接口/模块/数据）
3. 实施步骤
4. 验收标准
5. 风险与回滚
6. 观测指标
7. 发布说明

---

## 8. 发布门槛（DoD）

一次可发布优化必须同时满足：

1. 功能正确：关键路径手动与自动验证通过
2. 性能可接受：核心接口无明显退化
3. 安全合规：写接口鉴权无缺口
4. 可回滚：开关或脚本可快速恢复
5. 有文档：更新对应 roadmap 与运维说明

---

## 9. 风险清单与应对

1. 风险：大规模数据下 SQLite 写锁冲突
   - 应对：分批写入、重试指标、事务缩短
2. 风险：策略改动导致搜索/分类体验波动
   - 应对：灰度开关、golden set 回放、对比报告
3. 风险：安全配置漂移
   - 应对：启动自检 + CI 安全检查 + 文档约束
4. 风险：优化任务过大导致延期
   - 应对：按 Phase 切小、每周交付最小可用增量

---

## 10. 推荐执行顺序（从今天开始）

1. 先完成 P0：安全与构建门禁
2. 再做 P1：搜索与同步性能主链路
3. 同步推进测试与可观测性，避免“优化后不可验证”
4. 最后处理结构重构和长期能力

---

## 11. 附录：建议追踪面板字段

建议在任务看板统一使用以下字段：

1. `priority`（P0-P3）
2. `domain`（security/perf/search/classify/frontend/ops）
3. `owner`
4. `metric_before`
5. `metric_target`
6. `risk_level`
7. `rollback_ready`（yes/no）
8. `status`（todo/doing/review/done）

该面板可直接用于每周复盘，确保优化工作持续闭环。
