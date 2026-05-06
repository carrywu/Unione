# COCR-M21: Commercial OCR Blocked — Credential Missing

## Summary

M21 目标是继续推进商业 OCR 主链真实跑通。经现场盘点，**百度和腾讯 OCR credential 在所有可用源中均不存在**，主链继续处于 BLOCKED 状态。

- branch: `mimo`
- commit: `5be7193`
- date: `2026-05-06 11:56 CST`
- status: **BLOCKED / key_missing**
- route: **C (credential still missing)**

## 本轮接管起点

- branch: `mimo`
- commit: `5be7193` (基于 M20D 的 `821ed1d`)
- git status: clean（提交了 1 个 checkpoint fix 后）
- 上一轮报告：`.agent/handoff/real-commercial-ocr-provider-integration-20260506-041527.md`

## Credential 诊断

所有源均已检查，结果一致：**absent**。

| 源 | BAIDU_* | TENCENT_* | COMMERCIAL_OCR_* |
|---|---|---|---|
| Shell env | absent | absent | absent |
| `.env` (root) | absent | absent | absent |
| `backend/.env` | absent | absent | absent |
| `pdf-service/.env` | absent | absent | absent |
| `.env.local` | N/A (不存在) | N/A | N/A |
| `.env.commercial` | N/A (不存在) | N/A | N/A |
| `.agent/env` | N/A (不存在) | N/A | N/A |
| Backend DB | MySQL ECONNREFUSED | — | — |

### 缺失的具体变量

**百度 OCR：**
- `BAIDU_API_KEY`
- `BAIDU_SECRET_KEY`
- `BAIDU_ACCESS_TOKEN`（可选，API Key + Secret Key 可自动获取）

**腾讯 OCR：**
- `TENCENT_SECRET_ID`
- `TENCENT_SECRET_KEY`

## 本轮完成项

1. 现场盘点：git 状态、报告、credential、未提交修改
2. 确认 2 个未提交修改为合理修复（`provider_issue_reason` 在 status=ok/partial 时不应返回 `skipped_reason`）
3. 验证所有基础测试：17 passed（+1 新测试）
4. 验证 admin-web tsc + build：PASS
5. 验证 E2E stack script 语法：PASS
6. 提交 checkpoint：`5be7193`
7. 生成 env-diagnosis.masked.txt
8. 生成 debug 产物
9. 生成本 BLOCKED 报告

## 已验证通过项

| 验证项 | 结果 |
|---|---|
| pdf-service targeted pytest | 17 passed |
| admin-web tsc --noEmit | PASS |
| admin-web build | PASS (10.96s) |
| bash -n start-commercial-ocr-stack.sh | PASS |
| Playwright --list (workbench spec) | 1 test listed (M20D 验证) |

## BLOCKED 项

| 项目 | 状态 | 原因 |
|---|---|---|
| 百度 OCR 单页 smoke | BLOCKED | key_missing |
| 腾讯 OCR 单页 smoke | BLOCKED | key_missing |
| batch pages 1/6/16 | BLOCKED | key_missing |
| commercial-vs-local bbox compare | BLOCKED | 无商业 bbox 数据 |
| commercial fixture 生成 | BLOCKED | 无真实 OCR 结果 |
| workbench commercial E2E | BLOCKED | 无 fixture |
| VLM/LLM 复验 | BLOCKED | 无 commercial bbox |

## 用户补 Key 后的一键续跑命令

补完 key 后，按以下顺序执行：

```bash
# 1. 设置百度 credential（二选一）
export BAIDU_API_KEY="your_api_key"
export BAIDU_SECRET_KEY="your_secret_key"

# 或设置腾讯 credential
export TENCENT_SECRET_ID="your_secret_id"
export TENCENT_SECRET_KEY="your_secret_key"

# 2. 单页 smoke
cd /home/carry/project2/pdf-service
./.venv/bin/python scripts/run_real_commercial_ocr_smoke.py \
  --pdf '/home/carry/project2/题本/题本篇.pdf' --page 1 \
  --provider baidu_paper_cut_edu --real-smoke true

# 3. batch 1/6/16
./.venv/bin/python scripts/run_real_commercial_ocr_batch.py \
  --pdf '/home/carry/project2/题本/题本篇.pdf' --pages '1,6,16' \
  --provider baidu_paper_cut_edu --max-pages 3 --real-smoke true

# 4. bbox 对比
./.venv/bin/python scripts/compare_commercial_vs_local_bbox.py \
  'debug/real-commercial-ocr-smoke/current/batch-commercial-ocr-summary.json' \
  'debug/real-data-data-analysis/batch-tiben-selected/batch-ocr-summary.json'

# 5. 如果成功，设置 fixture 并跑 workbench E2E
export E2E_REAL_BATCH_FIXTURE_ROOT="debug/real-commercial-ocr-smoke/current"
export E2E_REAL_BATCH_FIXTURE_NAME="batch-commercial-ocr-summary"
export E2E_REAL_BATCH_EXPECTED_BBOX_SOURCE="baidu_paper_cut_edu"
cd /home/carry/project2
pnpm exec playwright test e2e/data-analysis-commercial-ocr-workbench.spec.ts --trace=on
```

## 当前不依赖 Key 的可继续任务

即使 credential 缺失，以下任务可以继续推进：

1. provider error 分类测试（auth_failed / quota_exhausted / timeout / empty_result）
2. env diagnosis 脚本增强
3. BLOCKED 报告自动生成
4. Playwright --list 验证
5. 文档补齐
6. whole-page understanding / semantic grouping / recrop-plan 产物格式定义
7. similarity schema 和 API 设计
8. review 前端 UI 改进（在 local OCR 数据上迭代）

## Debug 产物路径

```
debug/commercial-ocr/20260506-115600/
├── git-status.txt
├── env-diagnosis.masked.txt
├── test-results.txt
```

## 是否允许进入下一阶段

- 商业 OCR 主链：**NO**（credential 缺失）
- 不依赖 key 的增强：**YES**

## Git 状态

- committed: `5be7193 fix(pdf-service): clear skipped_reason when provider status is ok/partial`
- push: NO
- 未提交文件: 无（clean working tree）
- 未跟踪文件: `docs/COCR_M15_M19_step6托管目标.md`（参考文档，未处理）

## 下一轮目标

1. 等待用户提供百度或腾讯 credential
2. 补 key 后执行续跑命令
3. 同时继续不依赖 key 的 P2/P3 增强任务
