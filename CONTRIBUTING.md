# Contributing

感谢你关注 StarSorty。

本文档说明如何在本地开发、验证改动，并提交尽量清晰、可审阅的贡献。

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

- Python `3.11`
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

### 方式 B：分别启动前后端

后端：

```bash
cd api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 4321
```

前端：

```bash
cd web
npm install
npm run dev
```

## 目录说明

- `api/`：FastAPI 后端
- `web/`：Next.js 前端
- `scheduler/`：定时同步服务
- `docs/`：项目文档
- `evaluation/`：压测与离线评估脚本
- `scripts/`：跨平台开发脚本

更详细说明见：`docs/guides/project-structure.md`

## 开发原则

- 优先做小而明确的改动
- 先解决根因，避免只做表面补丁
- 不顺手修复无关问题，除非会直接阻塞当前改动
- 保持与现有代码风格一致
- 敏感配置不要写入仓库

## 提交前检查

### 后端测试

```bash
npm run api:test
```

### 前端质量检查

```bash
npm run web:lint
npm run web:build
```

### 压测脚本

仅在需要验证性能相关改动时运行；命令会优先使用本地可用 Python，不适合时回退到 Docker Python 3.11 容器。

```bash
npm run api:bench
```

### CI 对齐

当前 CI 会执行：

- `python -m pytest -q api/tests`
- `npm run lint`（`web/`）
- `npm run build`（`web/`）

对应配置见：`.github/workflows/ci.yml`

## 文档改动要求

如果你的改动影响以下内容，请同步更新文档：

- 新增或修改 API：更新 `docs/guides/api-reference.md`
- 新增或修改环境变量：更新 `docs/guides/configuration.md`
- 修改部署流程：更新 `docs/guides/deployment-operations.md`
- 修改目录结构或入口文件：更新 `docs/guides/project-structure.md`
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
- 修改文档导航时，请同步更新 `docs/README.md` 与相关索引页

## 相关阅读

- `README.md`
- `docs/README.md`
- `docs/guides/README.md`
- `docs/guides/project-structure.md`
- `.github/workflows/ci.yml`
