# Contributing

感谢你关注 StarSorty。

本文档说明如何在本地开发、验证改动，并提交尽量清晰、可审阅的贡献。

如果你只是想部署、初始化或日常使用实例，优先看 `README.md` 与 `docs/README.md`；本页只覆盖开发与提交流程。

## 贡献范围

欢迎提交：

- Bug 修复
- 文档改进
- 测试补充
- 前端体验优化
- 后端接口与性能改进
- 部署与运维相关改进

如果改动较大，建议先提交 issue 或说明目标范围，避免与现有规划冲突。

## 本地环境

### 基础依赖

- Python `3.11` - `3.13`
- Node.js `20`
- npm
- Docker / Docker Compose（推荐，用于完整联调）

### 拉起项目

```bash
git clone <your-fork-or-repo-url>
cd StarSorty
cp .env.example .env
```

然后根据需要选择以下方式：

### 方式 A：使用项目脚本

```bash
npm run start
npm run status
npm run stop
```

说明：

- 首次运行前，先执行 `npm run web:install`。
- `npm run start` 会自动把本地 SQLite 指到仓库内 `data/app.db`。
- 如果不确定本地环境状态，先跑 `npm run doctor`，细节统一看 `scripts/README.md`。
- 建议把仓库根目录脚本当作唯一验证入口，避免本地命令和 CI 行为漂移。
- Python/Docker fallback、前端依赖校验、web smoke 等运行时细节统一写在 `scripts/README.md`。

### 方式 B：分别启动前后端

后端：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r api/requirements-dev.txt
cd api
uvicorn app.main:app --reload --port 4321
```

如果你要重新建本地 Python 环境，统一从仓库根目录执行上面的 `python -m venv .venv`，不要再单独维护旧的 API 子目录环境。

如果直接在宿主机运行后端，把 `DATABASE_URL` 改成仓库内 `data/app.db` 的绝对路径；`.env.example` 中的 `sqlite:////data/app.db` 是 Docker / Compose 默认值。

前端：

```bash
npm run web:install
npm run web:dev
```

目录、关键入口与运行关系统一见 `docs/guides/project-structure.md`。

## 开发原则

- 优先做小而明确的改动
- 先解决根因，避免只做表面补丁
- 不顺手修复无关问题，除非会直接阻塞当前改动
- 保持与现有代码风格一致
- 敏感配置不要写入仓库

## 提交前检查

优先按下面顺序验证：

```bash
npm run docs:check
git diff --check
npm run scripts:test
npm run api:test
npm run smoke:e2e
npm run web:test
npm run web:lint
npm run web:build
npm run web:smoke
```

如果遇到文档坏引用、重复导航页、Python 版本不匹配、Docker fallback、前端依赖半安装、`doctor` 告警、清理或重置需求，先看 `scripts/README.md`。

### 压测脚本

仅在需要验证性能相关改动时运行；命令会优先使用本地可用 Python，不适合时回退到 Docker Python 3.11 容器。

```bash
npm run api:bench
```

### CI 对齐

当前 CI 会执行：

- `npm run docs:check`
- `git diff --check`
- `python -m pytest -q api/tests`
- `npm run smoke:e2e`
- `npm run test`（`web/`）
- `npm run lint`（`web/`）
- `npm run build`（`web/`）
- `npm run smoke`（`web/`）

对应配置见：`.github/workflows/ci.yml`

## 文档改动要求

如果你的改动影响以下内容，请同步更新文档：

- 新增、删除或重命名 `docs/guides/`、`docs/roadmap/` 文档：更新 `docs/README.md`，保证唯一索引不漏文档
- 新增或修改 API：更新 `docs/guides/api-reference.md`
- 新增或修改环境变量：更新 `docs/guides/configuration.md`
- 修改部署流程：更新 `docs/guides/deployment-operations.md`
- 修改目录结构或入口文件：更新 `docs/guides/project-structure.md`
- 修改共享运行态、缓存边界或多 worker 语义：更新 `docs/guides/runtime-consistency.md`
- 影响用户使用路径：更新 `docs/guides/user-manual.md` 或 `README.md`

## 提交建议

建议保持提交原子化，便于审阅：

- 一个提交只解决一个问题或一组强相关变更
- 提交信息尽量说明“做了什么”与“为什么”

示例：

- `fix(api): guard export endpoint with admin token`
- `docs: add configuration and deployment guides`
- `feat(web): improve failed repos admin workflow`

## Pull Request 建议

PR 描述建议包含：

- 背景与目标
- 主要改动点
- 是否涉及数据结构、配置或 API 变更
- 验证方式
- 是否需要补充部署或回滚说明

如果改动影响界面，建议附截图；如果改动影响接口，建议附请求示例。

## 注意事项

- 不要提交真实 token、密钥或生产配置
- 不要把本地数据库、日志或构建产物作为功能改动的一部分提交
- 涉及 SQLite 数据结构或迁移时，请明确说明兼容性影响
- 修改文档导航时，请同步更新 `docs/README.md` 与所有直接入口引用
