# 脚本目录说明

本文件是本地启动、测试命令和运行时兜底逻辑的权威说明。`README.md` 与 `CONTRIBUTING.md` 只保留入口，不再重复展开脚本细节。

## 结构

- `run-platform.js`：跨平台入口（自动按系统分发）
- `windows/`：PowerShell 脚本
- `unix/`：macOS/Linux Bash 脚本

## 启动与开发

```bash
npm run start
npm run status
npm run stop
npm run web:install
```

- `npm run start`：在宿主机启动本地开发栈，API 会默认把 SQLite 数据写到仓库内 `data/app.db`，不依赖容器内 `/data/app.db`。
- `npm run web:install`：从仓库根目录安装 `web` 依赖，供 `web:dev` / `web:lint` / `web:build` / `npm run start` 复用。

## 验证与回归

按文档执行验证时，统一使用下面顺序：

```bash
npm run docs:check
npm run scripts:test
npm run api:test
npm run web:test
npm run web:lint
npm run web:build
npm run web:smoke
```

- `npm run docs:check`：扫描文档中的仓库路径引用，阻止坏路径和重复文档索引页继续进入仓库。
- `npm run scripts:test`：运行脚本层 Node 回归测试，覆盖 Python/Docker 探测、Docker 权限回退与容器参数拼装逻辑。
- `npm run api:test` / `npm run api:bench`：优先使用本地 Python `3.11` - `3.13`；Python `3.14+` 会被直接判定为当前异步 SQLite 运行时不支持。脚本除了检查版本和依赖，还会实际探测 `aiosqlite` 连接；如果本地环境不适合运行，会打印逐项探测摘要，帮助快速定位卡点。
- 如果 Docker CLI 已安装但当前 shell 无法访问 Docker daemon，脚本会先自动尝试 `sg docker` 回退；若仍失败，会明确提示权限/daemon 状态，而不是笼统地显示 `docker: unavailable`。常见原因是刚加入 `docker` 用户组但还没重新登录。
- Docker fallback 会复用一个持久化 Docker volume 作为 pip 下载缓存，加速重复执行 `npm run api:test` / `npm run api:bench`。
- `npm run web:test`：运行前端纯逻辑回归测试，覆盖首页分页/轮询与详情页请求顺序保护。
- `npm run web:dev` / `npm run web:lint` / `npm run web:build`：在真正执行前会校验 `web/node_modules/.bin` 是否完整，避免半残安装直接炸掉。
- `npm run web:smoke`：启动生产模式 Next 服务，检查首页、管理页、设置页以及动态详情路由是否已经正确构建。
- `npm run api:bench`：只在需要确认性能回归时再运行，不属于日常提交流程必跑项。
- 压测报告默认输出到 `evaluation/benchmarks/latest-report.json`。

## 常见失败与处理

- `docs:check` 提示 missing path 或重复索引页：先修正文档里的路径引用，或删除 `docs/guides/README.md`、`docs/roadmap/README.md`、`docs/archive/README.md` 这类重复入口
- API 测试提示 Python `3.14+` 不支持：改用本地 Python `3.11` - `3.13`，或让脚本走 Docker Python 3.11 fallback
- Docker 已安装但脚本仍提示无法访问 daemon：确认当前 shell 已刷新 `docker` 用户组；必要时重新登录或重开 shell
- `web:test` 在受限环境里出现 IPC / `listen EPERM`：换到允许本地 IPC 的正常 shell 或 CI runner 再执行
- `web:smoke` 提示 `Timed out waiting for http://127.0.0.1:1234/`：确认环境允许本地端口绑定，并先完成 `npm run web:build`
- `web:lint` / `web:build` 提示 `eslint`、`next` 等命令不存在：重新执行 `npm run web:install`

## 可选平台命令

```bash
npm run start:win
npm run start:unix
```
