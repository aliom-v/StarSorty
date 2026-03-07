# 版本完善计划（2026-03）

本文档用于收敛当前版本的剩余问题，并作为后续执行顺序的依据。

## 目标

将当前版本从“可用的自用 / 内测版”提升到“更适合稳定交付与多人部署”的状态。

## 当前判断

当前版本已经具备以下基础能力：

- GitHub Star 同步
- 规则 / AI 分类
- 检索与筛选
- Obsidian 导出
- 个性化偏好与训练样本
- 基础部署文档与使用文档

但从发布完成度看，仍存在以下主要缺口：

1. 部分接口暴露面偏宽
2. 测试覆盖不足以支撑稳定发布
3. 前端缺少项目级测试
4. 发布管理资料还不完整
5. 工作区仍处于开发态，尚未收口为干净发布版本

## 发现的问题

### P1：需要优先处理的问题

#### 1. 公开配置接口暴露过多运行信息

- `api/app/routes/settings.py:45` 的 `GET /settings` 当前无需管理员权限。
- 接口会返回以下内部运行信息：
  - `github_username`
  - `github_target_username`
  - `github_usernames`
  - `github_mode`
  - `classify_mode`
  - `rules_json`
  - `sync_cron`
  - token 是否已配置

风险：

- 虽不直接泄露密钥，但会暴露实例内部配置边界。
- 对公网部署或多人共享部署不够保守。

建议：

- 将 `GET /settings` 收紧为管理员接口；或
- 拆分为公开版 `/api/config/client-settings` 与管理员版 `/settings`。

#### 2. 用户偏好与兴趣画像接口公开可读

- `api/app/routes/user.py:23` 的 `GET /preferences/{user_id}` 当前公开可读。
- `api/app/routes/user.py:74` 的 `GET /interest/{user_id}` 当前公开可读。

风险：

- 多用户实例中，任意调用方可读取某个 `user_id` 的偏好配置和兴趣画像。
- 隐私边界不清晰。

建议：

- 至少对读取接口增加管理员鉴权；或
- 引入用户级鉴权后，仅允许本人或管理员读取。

#### 3. 失败仓库列表为公开接口

- `api/app/routes/repos.py:136` 的 `GET /repos/failed` 当前无需管理员权限。

风险：

- 暴露分类失败样本与系统处理质量信息。
- 更接近运维 / 管理侧信息，而非公开查询能力。

建议：

- 改为管理员接口。

### P2：发布前建议补齐的问题

#### 4. API 测试覆盖不足

当前测试文件主要为：

- `api/tests/test_phase1_optimizations.py:1`
- `api/tests/test_phase3_stats_snapshot.py:1`
- `api/tests/test_phase3_consistency_report.py:1`
- `api/tests/test_security_baseline.py:1`

但实际路由模块为：

- `api/app/routes/sync.py:1`
- `api/app/routes/classify.py:1`
- `api/app/routes/repos.py:1`
- `api/app/routes/settings.py:1`
- `api/app/routes/stats.py:1`
- `api/app/routes/user.py:1`
- `api/app/routes/training.py:1`
- 以及其他路由模块

缺口：

- `sync` 路由缺少接口级测试
- `classify` 关键路径缺少更完整测试
- `repos` 查询 / override / README 补抓缺少接口级测试
- `user` 偏好、反馈、兴趣画像缺少接口级测试
- `settings` 读写缺少接口级测试

建议：

- 以路由层 smoke + 核心分支覆盖为第一阶段目标。

#### 5. 前端没有项目级自动化测试

- CI 当前只有 `pytest`、`web lint`、`web build`，见 `.github/workflows/ci.yml:1`。
- 未发现 `web/` 下项目自身的页面 / 交互测试文件。

风险：

- 前端回归基本依赖人工验证。
- 管理台与首页搜索的交互回归成本较高。

建议：

- 至少补最小 smoke 测试或关键页面交互测试。
- 第一阶段可从首页加载、管理台登录态、关键按钮流程开始。

### P3：发布收尾问题

#### 6. 版本发布材料不完整

- API 版本已更新为 `0.2.0`，见 `api/app/main.py`。
- 仓库已补充 `CHANGELOG.md` 作为发布说明入口。

影响：

- 版本变化缺少可追踪的发布说明。
- 后续升级、回归和对外说明不够清晰。

建议：

- 增加 `CHANGELOG.md`
- 明确当前版本号与发布说明

#### 7. 工作区仍处于开发态

- 当前仓库存在较多已修改 / 未跟踪文件，见 `git status` 检查结果。

影响：

- 不利于识别“哪些是本版本正式变更”。
- 发布前不利于做干净验收。

建议：

- 在功能收尾后整理发布批次
- 以“接口权限修复 / 测试补齐 / 文档发布”三个原子阶段收口

## 执行顺序

### 阶段 1：安全与暴露面收口

目标：先把不合适的公开接口收紧。

执行项：

1. 收紧 `GET /settings`
2. 收紧 `GET /preferences/{user_id}`
3. 收紧 `GET /interest/{user_id}`
4. 收紧 `GET /repos/failed`
5. 补对应接口测试
6. 更新 API 文档与用户手册

建议涉及文件：

- `api/app/routes/settings.py`
- `api/app/routes/user.py`
- `api/app/routes/repos.py`
- `api/tests/`
- `docs/guides/api-reference.md`
- `docs/guides/user-manual.md`

### 阶段 2：后端测试补齐

目标：让核心能力具备最低限度的回归保障。

优先补测顺序：

1. `sync`
2. `classify`
3. `repos`
4. `settings`
5. `user`

建议测试范围：

- 正常路径
- 鉴权失败路径
- 参数错误路径
- 冲突 / 重复提交路径
- 缓存失效或状态变更后的关键返回

### 阶段 3：前端最小回归保障

目标：降低 UI 回归风险。

建议先覆盖：

1. 首页初始加载
2. 搜索与筛选的基础流程
3. 管理台认证后关键区域是否可见
4. 同步 / 分类按钮的基础触发流程
5. 设置页基础状态展示

### 阶段 4：发布收尾

目标：形成更清晰的发布版本。

执行项：

1. 新增 `CHANGELOG.md`
2. 明确当前发布版本号
3. 检查 README / docs 与实现一致性
4. 运行完整验证
5. 整理干净的发布提交

## 验收标准

### 阶段 1 验收

- `GET /settings` 不再向匿名调用者暴露内部运行配置
- `GET /preferences/{user_id}` 与 `GET /interest/{user_id}` 权限边界明确
- `GET /repos/failed` 仅管理员可访问
- 新增或更新的接口权限变更已同步到文档

### 阶段 2 验收

- 核心后端路由具备基础接口测试
- `npm run api:test` 通过
- 高优先级鉴权接口至少覆盖正常 / 失败两类路径

### 阶段 3 验收

- 至少建立最小前端自动化回归能力
- 首页与管理台关键流程具备基础 smoke 覆盖

### 阶段 4 验收

- 存在 `CHANGELOG.md`
- 版本号与发布说明清晰
- `README.md` 与 `docs/` 不存在明显失配
- 发布前验证项通过：
  - `npm run api:test`
  - `npm run web:lint`
  - `npm run web:build`
  - `npm run web:smoke`

### 当前执行结论（更新于 2026-03-07）

- 阶段 1：已完成，公开配置与管理侧读取接口已按管理员边界收口。
- 阶段 2：已完成，`sync/classify/repos/settings/user` 已补最小路由回归覆盖。
- 阶段 3：已完成，首页、管理页、设置页已具备前端静态 smoke 校验。
- 阶段 4：已完成，版本号更新为 `0.2.0`，并补齐 `CHANGELOG.md` 与发布文档说明。

## 验证步骤

最终执行阶段建议使用以下检查：

```bash
npm run api:test
npm run web:lint
npm run web:build
```

如涉及性能相关修改，再补充：

```bash
npm run api:bench
```

## 不在本轮优先范围内

以下内容可以在当前版本稳定后再做：

- 更完整的用户级鉴权体系
- 更细粒度的角色权限控制
- 更系统的前端 e2e 覆盖
- 更完整的版本化发布流程

## 下一步

按本文档建议，下一步应从 **阶段 1：安全与暴露面收口** 开始执行。
