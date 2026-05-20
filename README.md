# 🌟 StarSorty

> **不再让你的 GitHub Star 吃灰。**
> 一个自托管的 GitHub Star 智能管理系统，利用 AI 自动分类、生成摘要，构建你的私人代码知识库。

---

## 目录

- [关于本项目](#-关于本项目)
- [核心功能](#-核心功能)
- [系统架构](#️-系统架构)
- [快速开始](#-快速开始)
- [常用操作](#-常用操作)
- [本地开发](#-本地开发)
- [文档导航](#-文档导航)
- [License](#-license)

---

## 📖 关于本项目

当前发布版本：`0.2.0`（2026-03-07）

开发者常常会 Star 很多有价值的仓库，但时间一长，收藏列表就会变得难搜、难筛、难回顾。

**StarSorty** 的目标不是简单“同步 Star”，而是把这些仓库整理成一个可检索、可分类、可回顾的私人知识库。

### 核心工作流

1. **同步**：定时从 GitHub 拉取 Star 仓库。
2. **理解**：读取仓库描述、主题和 README，并结合规则或 AI 做分类。
3. **整理**：生成分类、标签、关键词、摘要等结构化信息。
4. **使用**：通过 Web UI 或 API 检索、筛选、导出和维护这些仓库。

---

## ✨ 核心功能

- 🔄 **自动同步**：内置调度器，支持定时增量同步 GitHub Star。
- 🤖 **多模型 AI 支持**：支持 OpenAI、Anthropic，以及兼容 OpenAI 协议的第三方模型。
- 🏷️ **分类与标签体系**：输出分类、标签、关键词、中文摘要，支持人工覆盖修正。
- 🔍 **搜索与筛选**：支持关键词、标签、分类、语言、Star 数等多条件检索。
- 🧠 **个性化能力**：支持用户偏好映射、搜索反馈、点击反馈与兴趣画像。
- 📦 **导出与集成**：支持导出 Obsidian ZIP，用于构建个人知识库。
- 🐳 **自托管部署**：通过 Docker Compose 在单机 VPS 运行，数据保存在本地 SQLite。

### 当前版本重点

- 发布版本：`0.2.0`（2026-03-07）
- 新版分类链路：规则候选 + AI 仲裁 + 回退机制
- 新版搜索排序：相关度排序与命中原因展示
- 质量与一致性指标：`/metrics/quality`、`/metrics/consistency`
- 当前安全边界：`APP_ENV=production` 时会强制 `ADMIN_TOKEN` 与显式 CORS；Web 管理台已切到 cookie session + CSRF
- 用户偏好与训练样本：`/preferences`、`/interest`、`/training/*`
- 回归保障：API 路由 smoke、权限回归、前端构建 smoke、CI 门禁

更完整的接口与功能说明见：`docs/guides/api-reference.md`

---

## 🏗️ 系统架构

StarSorty 使用前后端分离 + 调度器的自托管架构：

- **Web**：Next.js 前端，负责检索、浏览和管理操作，Compose 中以 Next server 运行
- **API**：FastAPI 后端，负责同步、分类、检索、导出和配置
- **Database**：SQLite 持久化仓库、任务、设置与偏好数据
- **Scheduler**：定时调用 `/sync`，执行自动同步

默认端口：

- `1234`：Web
- `4321`：API

更详细的目录与模块关系见：`docs/guides/project-structure.md`

---

## 🚀 快速开始

推荐使用 Docker Compose 直接部署到单机 VPS，不再依赖额外的静态托管平台。

### 1. 克隆仓库

```bash
git clone https://github.com/aliom-v/StarSorty.git
cd StarSorty
```

### 2. 准备配置

```bash
cp .env.example .env
```

至少确认以下变量：

```env
GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
ADMIN_TOKEN=change_me
ADMIN_SESSION_TTL_HOURS=12
CORS_ORIGINS=http://localhost:1234
API_BASE_URL=http://api:4321
NEXT_PUBLIC_API_BASE_URL=http://localhost:4321

AI_PROVIDER=custom
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=sk-xxxx
AI_MODEL=deepseek-chat
```

说明：

- 生产环境请设置 `APP_ENV=production`
- 生产环境必须配置显式 `CORS_ORIGINS`，不能使用 `*`
- `API_BASE_URL` 给容器内的 scheduler 和服务端渲染中的 Web 使用，Compose 默认保持 `http://api:4321`
- `NEXT_PUBLIC_API_BASE_URL` 给浏览器使用；管理台登录依赖 cookie session，优先使用同域反代 `/api`，或至少保持 Web 与 API 处于 same-site 域名下
- AI 相关配置只从后端 `.env` 读取

完整变量说明见：`docs/guides/configuration.md`

按执行目标补齐变量：

- 只验证容器、`/health` 和首页：默认模板即可启动，但数据为空，`/auth/check` 会因为 `ADMIN_TOKEN` 未配置而返回 `503`。
- 需要本地管理写操作：配置 `ADMIN_TOKEN`；如果只是受信任的本地开发，也可以保持 `APP_ENV=development` 并临时开启 `ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV=true`。
- 需要真正同步 GitHub Star：至少提供一个同步目标。可直接配置 `GITHUB_USERNAME`、`GITHUB_TARGET_USERNAME` 或 `GITHUB_USERNAMES`；也可以只配置 `GITHUB_TOKEN`，系统会自动把该 token 对应账号作为同步目标。若已经配置了显式用户名，但还想把 token 对应账号也一并同步，再额外设 `GITHUB_INCLUDE_SELF=true`。
- 需要 AI 分类：`CLASSIFY_MODE=rules_only` 可直接使用内置规则；`rules_then_ai` 在缺少 AI 配置时会退回规则分类；`ai_only` 必须补齐 `AI_PROVIDER`、`AI_MODEL` 以及对应的密钥或自定义 `AI_BASE_URL`。
- 如果未配置 `GITHUB_TOKEN`，同步通常仍可运行，但分类阶段若开启 README 抓取，更容易撞到 GitHub 匿名速率限制；首次本地规则分类建议先把 `include_readme` 设成 `false`。

### 3. 启动服务

```bash
docker compose up -d --build
```

启动后访问：

- Web：`http://localhost:1234`
- API 文档：`http://localhost:4321/docs`

这套默认编排就是给小型 VPS 准备的：

- `1C1G` 可以跑低频同步和轻量使用
- `2C2G` 更稳，尤其是首次构建镜像和批量分类时
- 记得持久化 `data/` 和 `logs/`

### 4. 初始化数据

执行前确认：

- 当前实例如果 `ADMIN_TOKEN` 为空且未开启本地开发豁免，`POST /sync`、`POST /classify/background`、`PATCH /settings` 等写接口会直接返回 `503`。
- `POST /sync` 还需要至少一个 GitHub 同步目标，否则任务会失败并显示 `No GitHub usernames configured`。
- `POST /classify/background` 在 `CLASSIFY_MODE=ai_only` 且 AI 配置不完整时会失败；`rules_only` 和缺少 AI 的 `rules_then_ai` 都可以继续走规则分类。

先同步：

```bash
curl -X POST "http://localhost:4321/sync" \
  -H "X-Admin-Token: <ADMIN_TOKEN>"
```

再触发后台分类：

```bash
curl -X POST "http://localhost:4321/classify/background" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: <ADMIN_TOKEN>" \
  -d '{"limit":50,"concurrency":3}'
```

如果当前没有 `GITHUB_TOKEN`，建议首次先避免 README 抓取：

```bash
curl -X POST "http://localhost:4321/classify/background" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: <ADMIN_TOKEN>" \
  -d '{"limit":50,"concurrency":3,"include_readme":false}'
```

### 5. 验证部署结果

```bash
curl http://localhost:4321/health
curl http://localhost:4321/classify/status
curl http://localhost:1234
```

如果还需要继续检查：

- 浏览器访问首页、`/admin`、`/settings`
- 需要反向代理、升级、备份或排障时，看 `docs/guides/deployment-operations.md`

---

## 🛠️ 常用操作

> Web 页面中的写操作现在会先把 `ADMIN_TOKEN` 交换成浏览器 session cookie。CLI 和运维脚本仍然直接使用 `X-Admin-Token`。

### 查看同步状态

```bash
curl "http://localhost:4321/status"
```

### 查看分类状态

```bash
curl "http://localhost:4321/classify/status"
```

### 查询任务状态

```bash
curl "http://localhost:4321/tasks/<task_id>"
```

### 检索仓库

```bash
curl "http://localhost:4321/repos?q=go%20crawler&sort=relevance&limit=20"
```

更多 API 示例见：`docs/guides/api-reference.md`

---

## 💻 本地开发

README 只保留最短开发入口；完整阅读路径看 `docs/README.md`，贡献流程与脚本细节统一见 `CONTRIBUTING.md` 和 `scripts/README.md`。

### 一键启停（跨平台）

```bash
npm run start
npm run status
npm run stop
```

- 首次运行前，先执行 `npm run web:install` 安装前端依赖。
- `npm run start` / `npm run start:unix` / `npm run start:win` 会自动把本地 SQLite 指到仓库内 `data/app.db`。
- 想先确认本地环境是否正常，优先跑 `npm run doctor`；命令细节统一看 `scripts/README.md`。
- 建议统一从仓库根目录执行验证；文档引用校验、命令顺序、Python/Docker fallback、前端依赖校验和 smoke 细节统一看 `scripts/README.md`。
- 清理和重置命令统一看 `scripts/README.md`，默认清理不会碰 `.env`、`.venv` 或本地数据库。
- 需要分别启动前后端、调整宿主机 `DATABASE_URL` 或对齐 CI 流程时，直接看 `CONTRIBUTING.md`。

---

## 📚 文档导航

- `docs/README.md`：唯一文档入口与阅读路径
- `docs/guides/user-manual.md`：页面、管理台与常见操作流程
- `CONTRIBUTING.md`：本地开发、验证与提交流程
- `CHANGELOG.md`：最近版本与文档整理记录
- 历史迁移资产如确需追溯，可看 `archive/tag-id-migration/README.md`

---

## 📄 License

本项目采用 MIT License 开源。
