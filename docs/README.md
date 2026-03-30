# 文档导航

StarSorty 现在只保留一个文档总入口。跨文档阅读路径统一收口在本页，避免在 `README` 或各个 guide 里重复维护导航。

## 从哪里开始

### 我想先跑起来

1. `../README.md`
2. `guides/configuration.md`
3. `guides/deployment-operations.md`

### 我想理解当前系统和风险

1. `guides/project-structure.md`
2. `guides/api-reference.md`
3. `guides/runtime-consistency.md`
4. `guides/engineering-audit.md`

### 我想继续推进后续改造

1. `guides/engineering-audit.md`
2. `roadmap/current-priorities.md`
3. `roadmap/optimization-execution-plan.md`
4. `../CONTRIBUTING.md`

## 按文档执行的最短路径

### 我想部署一套可用实例

1. 按 `../README.md` 完成 `.env`、`docker compose up -d --build` 与首次同步
2. 需要确认变量含义时，看 `guides/configuration.md`
3. 需要同域 `/api` 反代或运维排障时，看 `guides/deployment-operations.md`

### 我想本地开发并验证改动

1. 按 `../CONTRIBUTING.md` 准备本地依赖和启动方式
2. 运行时限制、Python/Docker fallback、前端依赖校验统一看 `../scripts/README.md`
3. 验证顺序统一使用：

   ```bash
   npm run docs:check
   npm run scripts:test
   npm run api:test
   npm run web:test
   npm run web:lint
   npm run web:build
   npm run web:smoke
   ```

## 职责边界

- `../README.md`：项目介绍、快速开始、常用命令，只保留上手入口
- `../CONTRIBUTING.md`：本地开发、验证与提交流程
- `guides/`：当前仍然有效的说明型文档
- `roadmap/`：当前仍会执行的优先级与实施步骤
- `../scripts/README.md`：脚本和运行时兜底逻辑的权威说明
- `../archive/tag-id-migration/README.md`：历史迁移资产，仅用于追溯

## 文档维护约定

- `README.md` 保持“上手入口”定位，不承载所有细节。
- `docs/README.md` 是唯一文档索引入口；不要再新增 `guides/README.md`、`roadmap/README.md` 这类重复导航页。
- `guides/` 文档只写主题说明；不要再附一整套“推荐阅读顺序”“相关阅读”重复导航。
- `docs/guides/` 只放当前仍然有效的说明型文档。
- `docs/roadmap/` 只保留当前仍会执行的计划文档。
- 已过时但仍有追溯价值的材料移动到仓库根目录 `archive/`；没有保留价值的直接删除。
