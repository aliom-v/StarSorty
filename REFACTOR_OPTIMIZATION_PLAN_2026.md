# StarSorty 优化与重构完整计划（2026-02）

## 1. 背景与目标

StarSorty 当前已经具备可用闭环：同步 Star、分类、检索、人工覆盖、导出。  
但在“分类准确性”和“搜索命中体验”上，存在结构性问题，导致主观体验不稳定。

本计划的目标：

1. 明显提升分类可信度与可解释性（减少误分、空标签、过度泛化）。
2. 提升搜索“找得到 + 找得准”的一致性。
3. 建立可持续演进的架构（规则、AI、索引、评测解耦）。
4. 在不破坏现有数据的前提下完成渐进式迁移。

---

## 2. 当前问题诊断（基于现有代码）

### 2.1 规则标签与 taxonomy 标签体系不一致（高优先级）

- 规则标签来自 `api/config/rules.json`，如 `proxy`、`ai`、`llm` 等英文值。
- taxonomy 允许标签来自 `api/config/taxonomy.yaml`，多数为中文值（如 `代理`、`工具`）。
- `validate_classification` 会过滤不在 `tag_pool` 内的标签（`api/app/taxonomy.py`）。

影响：

1. 规则命中后可能出现“分类有了但标签为空”。
2. 标签云和标签检索价值下降。
3. 用户感知为“分类不细/不准”。

### 2.2 规则匹配策略过于激进（高优先级）

- `match_rule` 为 substring + 首条命中即返回（`api/app/rules.py`）。
- 在 `rules_then_ai` 模式下，命中规则后会直接写库并跳过 AI（`api/app/main.py`）。
- 存在“广覆盖关键词规则”（例如语言名规则）容易吞掉功能型分类。

影响：

1. 召回高但精准度下降。
2. 类别被“过早决定”，AI 无法纠偏。
3. 分类结果对规则顺序敏感。

### 2.3 搜索排序与过滤语义不够贴合“检索场景”（高优先级）

- `/repos` 默认按 `stargazers_count DESC` 排序（`api/app/db.py`）。
- 多标签筛选为 OR 语义（`api/app/db.py`），难以做“交集定位”。
- FTS 查询构造使用 AND 全词匹配，偏严格（`api/app/db.py`）。
- 目前缺少“相关度 + 活跃度 + 热度”的混合排序策略。

影响：

1. 搜索结果常被高星项目主导，不一定最相关。
2. 多标签筛选易“偏宽”，结果噪声偏大。
3. 用户会感知“搜出来了很多，但不是我想要的”。

### 2.4 分类流水线的可观测性不足（中高优先级）

- 已有失败计数与任务状态，但缺少结构化质量指标。
- 缺少“规则命中率、AI 回退率、标签空值率、置信度分布”看板。

影响：

1. 难以定位“模型问题还是规则问题”。
2. 优化后无法量化收益。

### 2.5 分类能力与展示能力耦合（中优先级）

- 目前标签值同时承担：存储语义、筛选语义、展示文案。
- 缺少“稳定内部标识 + 多语言显示层”的分层。

影响：

1. 未来扩展英文 UI、多语言或标签更名成本高。
2. 历史数据迁移风险高。

---

## 3. 优化总体策略

采用“两层分类 + 三段检索 + 可回放评测”的架构：

1. 分类层：
   - 规则引擎给候选（candidate generation）
   - AI 做最终判定（final decision）
2. 检索层：
   - 结构化过滤（category/subcategory/tags）
   - 全文召回（FTS）
   - 相关度重排（rank）
3. 评测层：
   - 黄金样本集（golden set）
   - 离线回放 + 在线指标

---

## 4. 分阶段实施计划

## Phase 0（1-2 天）：止血修复

目标：先修会直接拖垮结果质量的问题。

工作项：

1. 统一标签体系：
   - 新增 `tag_id` 概念（内部英文稳定值）。
   - rules 中标签改为 `tag_ids`，taxonomy 增加 `tag_defs`（`id`, `zh`, `group`）。
2. 兼容旧数据：
   - 增加旧标签映射表（old->id）。
   - 查询时双读，写入时规范化到 `tag_ids`。
3. 提供一次性迁移脚本：
   - 扫描 `ai_tags`、`override_tags`、规则配置。
   - 输出迁移报告（总量、失败量、未知标签）。

验收：

1. 新分类结果标签空值率显著下降。
2. 历史数据可无损查询。

## Phase 1（3-5 天）：分类链路重构

目标：从“规则一票通过”改为“规则辅助 + AI 仲裁”。

工作项：

1. 规则引擎升级：
   - 每条规则支持 `must_keywords`、`should_keywords`、`exclude_keywords`。
   - 输出候选分数，而不是立即定类。
2. 规则匹配改造：
   - substring 改为词边界/归一化 token 匹配。
   - 支持中英文分词归一化（轻量化优先）。
3. AI 提示词改造：
   - 输入包含“候选类别 + 证据片段 + 置信度”。
   - 要求返回“最终类别 + reason + 标签 + 关键词”。
4. 决策策略：
   - 高分规则可直出（可配置阈值）。
   - 中低分规则必须走 AI。
   - AI 失败时回退规则候选或标记待人工。

验收：

1. Top-1 类别准确率提升（对黄金集）。
2. 误分到 `uncategorized/other` 的比例下降。
3. 规则误命中率可观测。

## Phase 2（3-4 天）：检索与排序升级

目标：提升“搜得准”的体感。

工作项：

1. 查询语义增强：
   - `tag_mode=and|or`（默认 `or`，高级用户可切 `and`）。
   - `sort=relevance|stars|updated`。
2. 排序函数：
   - relevance = FTS 得分 + 分类置信度 + 关键词命中加权。
   - stars / updated 作为次级排序因子。
3. 索引优化：
   - 持续使用 FTS5。
   - 确认纳入 `readme_summary` 与规范化标签字段。
4. 前端交互优化：
   - 显示“为何命中”（匹配字段高亮、匹配标签）。
   - 标签筛选展示当前模式（AND/OR）。

验收：

1. 常见查询 Top10 命中率提升。
2. 用户连续二次搜索率下降（近似代表一次找准）。

## Phase 3（2-3 天）：可观测性与质量闭环

目标：把“感觉优化”变成“数据驱动优化”。

工作项：

1. 指标埋点：
   - `classification_total`, `rule_hit_rate`, `ai_fallback_rate`
   - `empty_tag_rate`, `uncategorized_rate`, `search_zero_result_rate`
2. 任务级日志结构化：
   - task_id、repo、rule_candidates、final_decision、latency。
3. 质量回放工具：
   - 输入固定 repo 集，输出前后 diff（类别、标签、关键词）。

验收：

1. 能在一次发布后明确回答“提升了什么、退化了什么”。

## Phase 4（按需）：领域化与个性化

目标：支持个人偏好分类，长期增强体验。

工作项：

1. 用户自定义标签映射与规则优先级。
2. “最近关注主题”自动学习（基于搜索/点击反馈）。
3. 人工覆盖反哺训练样本（用于规则优化与提示词 few-shot）。

---

## 5. 建议重构范围（模块级）

### 5.1 后端建议拆分模块

当前建议新增：

1. `api/app/classification/engine.py`
   - 统一 orchestrator，控制 rules/ai/fallback。
2. `api/app/classification/rule_matcher.py`
   - 仅负责规则匹配与打分。
3. `api/app/classification/decision.py`
   - 统一决策逻辑和阈值策略。
4. `api/app/search/ranker.py`
   - 统一相关度计算，避免 SQL 里散落逻辑。
5. `api/app/taxonomy/schema.py`
   - taxonomy/tag schema 校验与映射。

收益：

1. 降低 `main.py` 复杂度。
2. 分类策略可独立测试和迭代。

### 5.2 配置重构建议

1. `taxonomy.yaml` 改为：
   - `categories`（稳定 id）
   - `tag_defs`（id/name_zh/group）
2. `rules.json` 改为：
   - `rule_id`
   - `must/should/exclude`
   - `candidate_category/subcategory`
   - `tag_ids`
   - `priority`

### 5.3 数据库重构建议（渐进）

短期（兼容）：

1. 保留现有 `ai_tags/override_tags`，新增 `ai_tag_ids/override_tag_ids`。
2. 查询优先读新字段，不存在时回退旧字段。

中期（收敛）：

1. 最终统一为 `*_tag_ids`。
2. 展示层通过字典映射生成文案标签。

---

## 6. 质量评测方案（必须做）

建立 `evaluation/golden_set.json`（建议 200-500 条）：

1. 覆盖热门领域：AI、代理、DevTools、文档教程、媒体、安全等。
2. 每条标注：
   - expected category/subcategory
   - expected tags（可多值）
   - 搜索关键词样例

核心指标：

1. 分类：
   - category accuracy
   - subcategory accuracy
   - tag F1
2. 搜索：
   - query@10 命中率
   - zero-result rate
3. 稳定性：
   - 分类失败率
   - 平均分类耗时
   - AI 调用成本

---

## 7. 发布与回滚策略

1. 功能开关：
   - `CLASSIFY_ENGINE_V2_ENABLED`
   - `SEARCH_RANKER_V2_ENABLED`
2. 灰度发布：
   - 先对新同步数据启用。
   - 历史数据通过后台任务渐进重算。
3. 回滚机制：
   - 保留 v1 字段与 v1 查询路径。
   - 新旧结果可切换对比。

---

## 8. 风险与应对

1. 风险：规则改造初期误判波动。
   - 应对：黄金集回放 + 双轨输出对比。
2. 风险：标签迁移导致前端筛选异常。
   - 应对：双字段兼容 + 映射兜底 + 迁移报告。
3. 风险：搜索排序变更影响用户预期。
   - 应对：提供 `sort` 可选项，默认逐步切换。

---

## 9. 落地执行清单（按优先级）

P0（本周）：

1. 统一标签 ID 体系（规则/taxonomy/存储）。
2. 完成数据迁移脚本与迁移报告。
3. 修复规则命中后空标签问题。

P1（下周）：

1. 规则打分引擎（must/should/exclude）。
2. AI 仲裁与回退策略。
3. 黄金集评测脚本。

P2（后续）：

1. 相关度排序与 AND/OR 标签筛选。
2. 可观测性指标与质量看板。
3. 个性化分类增强。

---

## 10. 建议结论（简版）

当前最值钱的重构不是“换模型”，而是：

1. 统一标签语义层（id 与展示分离）。
2. 把规则从“终裁”改成“候选”。
3. 把搜索从“按星排序”升级为“相关度排序”。

这三件完成后，StarSorty 的主观体验会从“能用”提升到“可靠”。
