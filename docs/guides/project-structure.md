# 项目结构说明

## 顶层目录

- `api/`：FastAPI 后端服务（同步、分类、检索接口）
- `web/`：Next.js 前端页面与交互逻辑
- `scheduler/`：定时任务触发器
- `data/`：SQLite 数据与运行时持久化目录
- `logs/`：本地日志输出目录
- `evaluation/`：离线评测、回放与压测脚本
- `openspec/`：需求变更与规范草案
- `scripts/`：开发辅助脚本
  - `scripts/windows/`：Windows PowerShell 脚本
  - `scripts/unix/`：macOS/Linux Bash 脚本
  - `scripts/run-platform.js`：跨平台统一入口
- `docs/`：项目文档（路线图与指南）

## 关键入口文件

- `README.md`：项目总览、快速开始与常用命令
- `docker-compose.yml`：本地与自托管默认编排方式
- `api/app/main.py`：API 入口与中间件挂载
- `api/app/routes/__init__.py`：全部路由注册位置
- `api/app/config.py`：运行时配置读取入口
- `scheduler/main.py`：定时同步调度器入口
- `web/app/page.tsx`：前端首页入口
- `web/app/admin/page.tsx`：管理员控制台入口
- `web/app/settings/page.tsx`：设置与状态页面入口

## 后端模块概览

- `api/app/routes/`：HTTP 路由层，负责参数校验与响应组装
- `api/app/db/`：SQLite 数据访问与查询逻辑
- `api/app/classification/`：规则匹配、分类决策与 AI 协同逻辑
- `api/app/search/`：搜索重排与相关度解释
- `api/config/`：taxonomy、规则与标签定义
- `api/tests/`：后端回归测试

## 前端页面概览

- `/`：仓库检索与列表浏览
- `/repo`：仓库详情页
- `/admin`：同步、分类、失败仓库、导出、设置、个性化管理
- `/settings`：运行配置与 token 状态概览

## 数据与运行关系

- `web` 通过 `NEXT_PUBLIC_API_BASE_URL` 调用 `api`
- `scheduler` 按 `SYNC_CRON` 定时请求 `api:/sync`
- `api` 读写 `data/` 下 SQLite 数据库，并在 `logs/` 输出日志
- `evaluation/` 脚本用于对 API 性能和分类效果做离线验证

## 关键运行端口

- `4321`：后端 API
- `1234`：前端 Web

## 推荐阅读顺序

1. `README.md`
2. `docs/README.md`
3. `docs/guides/configuration.md`
4. `docs/guides/api-reference.md`
5. `docs/guides/deployment-operations.md`
6. `docs/roadmap/comprehensive-optimization-plan-2026.md`

## 相关阅读

- `README.md`
- `docs/README.md`
- `docs/guides/api-reference.md`
- `docs/guides/configuration.md`
