# StarSorty 优化计划

## 项目概述
StarSorty 是一个自托管的 GitHub Star 智能管理系统，使用 AI 自动分类和生成摘要。

---

## 执行状态: ✅ 全部完成

---

## 一、Bug 修复 (高优先级) - ✅ 全部完成

### 1.1 后端 Bug

#### BUG-001: ai_client.py - JSON 提取逻辑脆弱 ✅ 已修复
**文件**: `api/app/ai_client.py:119-154`
**问题**: Markdown 代码块提取逻辑在特殊情况下会失败
**修复**: 新增 `_strip_code_block()` 函数，正确处理 ```json 等语言标识符

#### BUG-002: ai_client.py - 异常重新抛出丢失堆栈 ✅ 已修复
**文件**: `api/app/ai_client.py:535, 564, 763, 791`
**问题**: `raise exc` 应改为 `raise` 以保留完整堆栈跟踪
**修复**: 将所有 `raise exc` 改为 `raise`

#### BUG-003: main.py - 后台任务无错误追踪 ✅ 已修复
**文件**: `api/app/main.py:603-610`
**问题**: `asyncio.create_task()` 是 fire-and-forget，异常会被静默吞掉
**修复**: 添加 `_handle_task_exception()` 回调函数记录异常

#### BUG-004: github.py - 不可达代码 ✅ 已修复
**文件**: `api/app/github.py:171`
**问题**: `raise RuntimeError()` 永远不会执行
**修复**: 改为安全的 `return response` 并添加注释

#### BUG-005: config.py - 默认值不一致 ✅ 已修复
**文件**: `api/app/config.py:125-138`
**问题**: `classify_mode` 默认值在函数签名和实际调用不一致
**修复**: 统一默认值为 `ai_only`

### 1.2 前端 Bug

#### BUG-006: admin/page.tsx - 错误的加载提示 ✅ 已修复
**文件**: `web/app/admin/page.tsx:89`
**问题**: 加载设置时显示 `t("loadingRepos")`，语义不正确
**修复**: 添加 `loadingSettings` 翻译键并使用

---

## 二、代码质量优化 - ✅ 全部完成

#### OPT-001: config.py - 静默异常吞噬 ✅ 已修复
**文件**: `api/app/config.py:45-48`
**修复**: 添加 `logger.warning()` 记录异常

#### OPT-002: db.py - 类型注解问题 ✅ 已修复
**文件**: `api/app/db.py:21-26`
**问题**: 使用 `callable` 而非 `Callable`
**修复**: 导入并使用 `typing.Callable`

#### OPT-003: ai_client.py - 类型注解不正确 ✅ 已修复
**文件**: `api/app/ai_client.py:335, 425, 521, 550`
**问题**: `taxonomy` 参数类型注解与实际结构不匹配
**修复**: 改为 `Dict[str, Any]`

#### OPT-004: db.py - 死代码 ✅ 已修复
**文件**: `api/app/db.py:394`
**问题**: `if not fields` 永远不会为 True
**修复**: 移除死代码

---

## 三、安全加固 - ✅ 全部完成

#### SEC-001: SQL LIKE 通配符注入 ✅ 已修复
**文件**: `api/app/db.py:757-758`
**问题**: 用户搜索词中的 `%` 和 `_` 会被解释为通配符
**修复**: 添加 `_escape_like()` 函数转义特殊字符

#### SEC-002: 空 Admin Token 警告 ✅ 已修复
**文件**: `api/app/main.py:131-145`
**问题**: ADMIN_TOKEN 未设置时无任何提示
**修复**: 添加警告日志提醒用户配置

---

## 四、性能优化 - ✅ 全部完成

#### PERF-001: 数据库索引 ✅ 已修复
**文件**: `api/app/db.py:279-286`
**修复**: 添加 `idx_repos_stargazers` 和 `idx_repos_summary_zh` 索引

#### PERF-002: 前端标签组渲染优化 ✅ 已修复
**文件**: `web/app/page.tsx:830-838`
**修复**: 使用 `useMemo` 预计算 `tagGroupsWithCounts`

---

## 五、资源管理 - ✅ 全部完成

#### RES-001: 后台任务资源泄漏 ✅ 已修复
**文件**: `api/app/main.py:71-85`
**问题**: 应用关闭时 `classification_task` 未被取消
**修复**: 在 lifespan 关闭时取消任务

#### RES-002: 前端重复数据 ✅ 已修复
**文件**: `web/app/page.tsx:408-415`
**问题**: 追加加载时可能出现重复项
**修复**: 使用 Set 去重

#### RES-003: useEffect 依赖问题 ✅ 已修复
**文件**: `web/app/page.tsx:620-645`
**问题**: `wasBackgroundRunning` 既是依赖项又在 effect 内被设置
**修复**: 改用 `useRef` 存储前一状态

---

## 六、代码注释改进 - ✅ 已完成

#### DOC-001: github.py TOCTOU 注释 ✅ 已添加
**文件**: `api/app/github.py:19-28`
**修复**: 添加注释说明 TOCTOU 是良性的设计决策

---

## 修复文件清单

| 文件 | 修改内容 |
|------|----------|
| `api/app/ai_client.py` | JSON 提取逻辑、异常堆栈、类型注解 |
| `api/app/github.py` | 死代码移除、TOCTOU 注释 |
| `api/app/main.py` | 后台任务错误回调、资源泄漏、Admin Token 警告 |
| `api/app/config.py` | 默认值统一、错误日志 |
| `api/app/db.py` | 死代码移除、SQL 注入防护、索引优化、类型注解 |
| `web/app/lib/i18n.tsx` | 添加翻译键 |
| `web/app/admin/page.tsx` | 加载提示文案 |
| `web/app/page.tsx` | 标签组渲染优化、重复数据去重、useEffect 依赖修复 |

---

## 总计

- **Bug 修复**: 6 个
- **代码质量优化**: 4 个
- **安全加固**: 2 个
- **性能优化**: 2 个
- **资源管理**: 3 个
- **文档改进**: 1 个

**共计修复 18 个问题，涉及 8 个文件**

---

*生成时间: 2026-01-30*
*完成时间: 2026-01-30*
