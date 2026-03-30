# RTK Repo Notes

- 优先使用仓库根目录脚本做验证：`npm run api:test`、`npm run web:test`、`npm run web:lint`、`npm run web:build`。
- 脚本层回归使用 `npm run scripts:test`，覆盖 Python/Docker 运行时探测与 Docker 组权限回退。
- `web` 相关命令默认要求先安装前端依赖；从仓库根目录执行 `npm --prefix web install`。
- API 测试与压测脚本会优先探测本地 Python `3.11` - `3.13` + `api/requirements-dev.txt`；Python `3.14+` 在当前异步 SQLite 运行时上被视为不支持并会直接拦截，不可用时再回退 Docker，且 Linux 下会在需要时自动尝试 `sg docker`。
- 首页保持分层：`web/app/page.tsx` 只负责组合视图，数据请求与轮询逻辑继续收敛在 `web/app/lib/useHomePageData.ts`。
- 修改脚本、本地开发流程或校验命令时，同步更新 `README.md`、`CONTRIBUTING.md`、`scripts/README.md`。
