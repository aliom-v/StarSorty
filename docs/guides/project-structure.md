# 项目结构说明

## 顶层目录

- `api/`：FastAPI 后端服务（同步、分类、检索接口）
- `web/`：Next.js 前端页面与交互逻辑
- `scheduler/`：定时任务触发器
- `scripts/`：开发辅助脚本
  - `scripts/windows/`：Windows PowerShell 脚本
  - `scripts/unix/`：macOS/Linux Bash 脚本
  - `scripts/run-platform.js`：跨平台统一入口
- `docs/`：项目文档（路线图与指南）

## 关键运行端口

- `4321`：后端 API
- `1234`：前端 Web

## 推荐阅读顺序

1. `README.md`
2. `docs/README.md`
3. `docs/roadmap/practical-optimization-plan.md`
