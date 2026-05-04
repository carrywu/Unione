# Project2 环境修复报告（收尾版）

更新时间：2026-05-02 17:36
项目路径：`/home/carry/project2`

## 1. 环境总状态
结论：部分可用（可进入业务修复阶段）。

- 开发环境可启动、可访问、可构建。
- 四服务与 Docker 组件健康检查通过。
- PDF 解析链路已跑通到“创建任务 + backend 调用 pdf-service + DB 任务入库”，但本轮 smoke 的最新任务在观察窗口内停留 `processing(10%)`，未完成收敛，需继续观察/排障。

## 2. 四个服务状态
基于 `bash /home/carry/project2/check-dev.sh`（见 `debug/pdf-smoke/20260502-continue/final-check-dev.txt`）：

- pdf-service `:8001`：PASS（`/health` = 200）
- backend `:3010`：PASS（`/api-docs` = 200）
- admin-web `:5173`：PASS（首页 200）
- h5-web `:5174`：PASS（首页 200）

## 3. Docker / Postgres / Redis 状态
- `project2-postgres`：Up（5432 暴露）
- `project2-redis`：Up（6379 暴露）
- 未删除任何 Docker volume。

## 4. 构建结果
构建日志：`/home/carry/project2/debug/autofix/20260502-124734/phase6-build.log`

- backend: `pnpm run build` 通过
- admin-web: `pnpm run build` 通过
- h5-web: `pnpm run build` 通过
- pdf-service: `python -c "from main import app; print(app.title)"` 通过（`Quiz PDF Service`）

## 5. 浏览器验证结果（phase7）
证据目录：`/home/carry/project2/debug/browser-check/20260502-130825/`

- `http://localhost:5173`：可访问（登录页）
- `http://localhost:5174`：可访问（登录页）
- `http://localhost:3010/api-docs`：可访问（Swagger UI）
- `http://localhost:8001/health`：可访问（`{"status":"ok"}`）

特别说明：
- `http://localhost:3010/api/docs` 返回 404（`Cannot GET /api/docs`）
- 正确 Swagger 地址是 `http://localhost:3010/api-docs`

## 6. PDF smoke test 结果（phase8）
证据目录：`/home/carry/project2/debug/pdf-smoke/20260502-continue/`

已生成文件：
- `upload-request.txt`
- `upload-response.json`
- `api-response.txt`
- `backend-log-tail.txt`
- `pdf-service-log-tail.txt`
- `db-task-check.txt`
- `smoke-result.md`
- 附加：`backend-pdf-conn.txt`、`pdf-service-connections.txt`

关键结果：
- 上传接口成功，返回本地 uploads URL。
- 解析接口成功，返回 task_id。
- `parse_tasks` 记录新增（本轮前后从 47 到 48）。
- backend 与 pdf-service 存在实时连接，pdf-service 存在外连 AI 服务连接。
- 最新 smoke 任务：`64bc9aeb-a638-4fd4-9ff2-0e673447a686`，当前状态 `processing`（10%）。

本轮额外修复：
- 为 pdf-service 安装 socks 依赖：`socksio`、`httpcore[socks]`、`httpx[socks]`。
- 重启四服务后复检通过。

## 7. 启停/检查脚本
脚本路径：
- `/home/carry/project2/start-dev.sh`
- `/home/carry/project2/stop-dev.sh`
- `/home/carry/project2/check-dev.sh`

用法：
- 启动：`bash /home/carry/project2/start-dev.sh`
- 停止：`bash /home/carry/project2/stop-dev.sh`
- 检查：`bash /home/carry/project2/check-dev.sh`

说明：
- 不会删除数据库 volume。
- 不会删除 uploads。
- 不会删除迁移包。

## 8. 未解决 blocker
1) PDF 解析任务长时间停留 `processing(10%)`（示例 task_id：`64bc9aeb-a638-4fd4-9ff2-0e673447a686`、`475a57d7-20e2-4768-9126-ce040c769b7a`）。
2) 部分历史任务存在 `未解析到题目`（属于业务/模型结果质量问题）。
3) `DEEPSEEK_API_KEY` 为空（本机 `DASHSCOPE_API_KEY` 已设置），如后续策略强依赖 deepseek，将成为外部能力 blocker。

## 9. 是否可以进入业务修复阶段
可以。

建议顺序：
1. 继续盯一个新 task 的完整生命周期（processing -> done/failed）。
2. 若持续卡住，定位 pdf-service 内部阶段耗时与超时策略（下载、页解析、模型调用、回传）。
3. 再进入解析质量（题目提取率/错题归档/前端展示）业务修复。