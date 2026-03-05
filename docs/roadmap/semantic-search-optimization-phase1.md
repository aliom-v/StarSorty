# 语义检索优化实施方案（Phase 1）

## 1. 目标

本阶段目标是提升 StarSorty 检索的“可用性”和“稳定性”，优先解决：

1. 结果相关性不稳定（只靠单一语义分）
2. 历史数据 embedding 缺失导致召回效果下降

## 2. 范围

Phase 1 只做两件事：

- H1：混合排序（Hybrid Ranking）
- H2：Embedding 回填任务（Backfill）

不在本阶段：

- 向量数据库替换
- 学习排序（LTR）
- 用户反馈训练

## 3. 设计说明

## 3.1 混合排序（H1）

接口：`GET /search/semantic`

排序分由四部分组成：

- `semantic_score`：语义向量相似度（余弦）
- `lexical_score`：关键词命中分（字段加权）
- `freshness_score`：新鲜度分（最近更新时间衰减）
- `hotness_score`：热度分（star/fork 对数归一）

组合公式（Phase 1）：

`final_score = 0.56*semantic + 0.28*lexical + 0.10*freshness + 0.06*hotness`

字段命中权重（lexical）示例：

- full_name / name：高权重
- description / readme_summary：中高权重
- topics / tags：中权重
- category / subcategory：中低权重

## 3.2 Embedding 回填任务（H2）

新增任务类型：`embedding_backfill`

新增接口：

- `POST /embedding/backfill`
  - 请求：`batch_size`, `only_missing`, `cursor_full_name`
  - 返回：任务 ID（走现有 task 体系）
- `GET /tasks/{task_id}`
  - 复用现有任务状态查询
- `POST /tasks/{task_id}/retry`
  - 支持对 `embedding_backfill` 任务重试

行为：

- 批量扫描仓库并重建 `summary_embedding`
- 支持断点（`cursor_full_name`）继续
- 支持仅回填缺失 embedding（`only_missing=true`）

## 4. 数据层改动

`repos.summary_embedding` 作为稀疏向量 JSON 存储。

触发更新时机：

- 同步 upsert 新仓库
- 分类结果更新（AI/rules）
- README 摘要更新
- 手动 override 更新

## 5. 验收标准

- 检索结果：同一查询下 Top10 相关性稳定提升
- 回填任务：可启动、可断点续跑、可重试
- 兼容性：原 `/repos` 接口行为不变
- 安全性：仅管理员可触发回填

## 6. 实施状态

- [x] H1 混合排序接入 `/search/semantic`
- [x] H2 回填任务与 API 接入
- [x] 任务重试支持 `embedding_backfill`
- [ ] 指标看板（P95/空结果率/点击率）

## 7. 下一阶段（Phase 2）

- ✅ 返回“命中原因”用于可解释性（已在 Phase 2 完成）
- ✅ 增加检索结果缓存层（已在 Phase 2 完成）
- ⏳ 引入用户反馈权重调优（待后续阶段）
