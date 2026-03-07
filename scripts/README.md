# 脚本目录说明

## 结构

- `run-platform.js`：跨平台入口（自动按系统分发）
- `windows/`：PowerShell 脚本
- `unix/`：macOS/Linux Bash 脚本

## 常用命令

```bash
npm run start
npm run status
npm run stop
```

测试与验证命令：

```bash
npm run api:test
npm run web:lint
npm run web:build
npm run web:smoke
npm run api:bench
```

- `npm run api:test`：优先使用本地可用 Python；如当前环境不适合运行 API 测试，会回退到 Docker Python 3.11 容器。
- `npm run web:smoke`：检查导出后的首页、管理页、设置页静态产物。
- `npm run api:bench`：优先使用本地可用 Python；如当前环境不适合运行压测，会回退到 Docker Python 3.11 容器。
- 压测报告默认输出到 `evaluation/benchmarks/latest-report.json`。

可选平台命令：

```bash
npm run start:win
npm run start:unix
```
