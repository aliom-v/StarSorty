# 语义检索优化实施方案（Phase 2）

## 1. 目标

在 Phase 1 基础上继续提升检索可用性，重点解决：

1. 结果为什么出现不可解释
2. 高频查询重复计算浪费资源

## 2. 范围

Phase 2 聚焦两项能力：

- E1：命中原因返回（Explainability）
- E2：语义检索缓存（Cache）

## 3. 设计与实现

## 3.1 命中原因返回（E1）

接口：`GET /search/semantic`

新增返回字段：

- `semantic_score`: 综合相关分
- `semantic_reasons`: 命中原因代码数组（最多 3 条）

原因代码：

- `name_match`
- `tag_match`
- `summary_match`
- `category_match`
- `high_semantic_similarity`
- `recently_updated`
- `popular_project`
- `semantic_related`

前端将代码映射为中英文可读文案并展示。

## 3.2 语义检索缓存（E2）

缓存粒度：完整查询参数（`q + filters + pagination`）

策略：

- 内存 TTL 缓存
- 默认 TTL：90 秒
- 默认容量：300 条
- 超限时淘汰最旧条目

配置项：

- `SEMANTIC_CACHE_TTL_SECONDS`
- `SEMANTIC_CACHE_MAX_ENTRIES`

失效策略：

以下变更会主动清空缓存：

- `sync` 触发
- `classify/classify/background` 触发
- `embedding/backfill` 触发
- 手动 override 更新
- README 摘要更新
- classify/backfill retry

## 4. 验收标准

- 同一查询在短时间重复请求应命中缓存
- API 返回 `semantic_reasons` 且前端可见
- 不影响原 `/repos` 搜索行为
- 缓存可通过配置项调整

## 4.1 API 快速示例

语义检索：

```bash
curl "http://localhost:4321/search/semantic?q=go%20crawler&limit=20"
```

触发回填：

```bash
curl -X POST "http://localhost:4321/embedding/backfill" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: <ADMIN_TOKEN>" \
  -d '{"batch_size": 200, "only_missing": true}'
```

## 5. 实施状态

- [x] E1 后端原因代码生成
- [x] E1 前端文案映射与展示
- [x] E2 TTL 缓存接入语义检索
- [x] E2 关键写路径主动失效

## 6. 下一步建议

- 增加缓存命中率指标
- 返回更细粒度的得分拆解（调试模式）
- 引入二级缓存（进程外）以支持多实例
