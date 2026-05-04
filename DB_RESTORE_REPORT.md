# Project2 数据库恢复报告（真实数据恢复）

更新时间：2026-05-02 17:36

## 1. 数据库基础信息
- 数据库类型：Postgres
- 数据库名：`quiz_app`
- 容器：`project2-postgres`

## 2. 是否找到真实数据库
- 结论：是。
- 真实数据来源：`/home/carry/postgres-current-all.sql.gz`

## 3. 搜索范围（已执行）
本次恢复过程中已覆盖以下路径进行数据库资产搜索（详见证据文件）：
- `/home/carry/下载/project2-migration`
- `/home/carry/project2`
- `/home/carry/下载`
- `/home/carry`
- Docker 相关数据线索（volume/容器）

证据文件：
- `/home/carry/project2/debug/db-restore/20260502-124917/db-assets-search.txt`

## 4. 候选与采用资产
- 已采用真实数据 dump：`/home/carry/postgres-current-all.sql.gz`
- 恢复前备份：`/home/carry/project2/debug/db-restore/20260502-124917/quiz_app-before-restore.dump`
- 恢复过程产物：`/home/carry/project2/debug/db-restore/20260502-124917/quiz_app-source-realdata.dump`

## 5. 恢复方式
- 先做临时校验，再执行正式恢复。
- 正式恢复前先备份当前库（见上文备份路径）。
- 恢复后进行了关键表计数和任务抽样核验。

## 6. 是否执行 seed
- 否。
- 本轮未执行 `pnpm run seed`。

## 7. 恢复后关键表数量
恢复完成后的基线核验（本轮收尾前已确认）：
- materials = 35
- parse_tasks = 44
- question_banks = 37
- questions = 208
- system_configs = 9
- user_records = 1510
- users = 11

收尾阶段说明：
- 因执行 PDF smoke test，`parse_tasks` 后续增加到 48（新增为测试任务记录），
  其他核心业务表规模保持一致。
- 最新核验文件：`/home/carry/project2/debug/db-restore/20260502-124917/final-db-check.txt`

## 8. 证据目录
- `/home/carry/project2/debug/db-restore/20260502-124917/`

目录关键文件：
- `db-assets-search.txt`
- `quiz_app-before-restore.dump`
- `quiz_app-source-realdata.dump`
- `final-db-check.txt`

## 9. 明确结论
本次是“真实 dump 恢复”，不是演示 seed 初始化。
