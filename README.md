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
- 🐳 **自托管部署**：通过 Docker Compose 运行，数据保存在本地 SQLite。

### 当前版本重点

- 发布版本：`0.2.0`（2026-03-07）
- 新版分类链路：规则候选 + AI 仲裁 + 回退机制
- 新版搜索排序：相关度排序与命中原因展示
- 质量与一致性指标：`/metrics/quality`、`/metrics/consistency`
- 默认安全基线：生产环境强制 `ADMIN_TOKEN`，公开暴露面已收口
- 用户偏好与训练样本：`/preferences`、`/interest`、`/training/*`
- 回归保障：API 路由 smoke、权限回归、前端静态 smoke、CI 门禁

更完整的接口与功能说明见：`docs/guides/api-reference.md`

---

## 🏗️ 系统架构

StarSorty 使用前后端分离 + 调度器的自托管架构：

- **Web**：Next.js 前端，负责检索、浏览和管理操作
- **API**：FastAPI 后端，负责同步、分类、检索、导出和配置
- **Database**：SQLite 持久化仓库、任务、设置与偏好数据
- **Scheduler**：定时调用 `/sync`，执行自动同步

默认端口：

- `1234`：Web
- `4321`：API

更详细的目录与模块关系见：`docs/guides/project-structure.md`

---

## 🚀 快速开始

推荐使用 Docker Compose 部署。

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
CORS_ORIGINS=http://localhost:1234

AI_PROVIDER=custom
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=sk-xxxx
AI_MODEL=deepseek-chat
```

说明：

- 生产环境请设置 `APP_ENV=production`
- 生产环境必须配置显式 `CORS_ORIGINS`，不能使用 `*`
- AI 相关配置只从后端 `.env` 读取

完整变量说明见：`docs/guides/configuration.md`

### 3. 启动服务

```bash
docker compose up -d --build
```

启动后访问：

- Web：`http://localhost:1234`
- API 文档：`http://localhost:4321/docs`

### 4. 初始化数据

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

---

## 🛠️ 常用操作

> Web 页面中的写操作需要 Admin token。你可以在设置页或管理页录入该 token。

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

### 一键启停（跨平台）

```bash
npm run start
npm run status
npm run stop
```

### 后端

```bash
cd api
python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --reload --port 4321
```

### 前端

```bash
cd web
npm install
npm run dev
```

更多开发与脚本说明：

- `scripts/README.md`
- `docs/guides/project-structure.md`
- `docs/guides/configuration.md`

---

## 📚 文档导航

- `docs/README.md`：文档总入口与阅读路径
- `docs/guides/README.md`：稳定指南索引
- `docs/roadmap/README.md`：路线图与规划索引
- `docs/guides/project-structure.md`：项目结构说明
- `docs/guides/user-manual.md`：用户使用手册
- `docs/guides/api-reference.md`：后端 API 接口总览与调用约定
- `docs/guides/configuration.md`：`.env` 与运行时配置参考
- `docs/guides/deployment-operations.md`：Docker 部署、备份、升级与排障
- `CHANGELOG.md`：版本变更记录与发布说明

---

## 📄 License

本项目采用 MIT License 开源。
