# Resume Prompt: COCR-M21

你是本项目 Agent，从 COCR-M21 续跑。
分支: mimo, commit: 5be7193
状态: 商业 OCR BLOCKED (key_missing), 基础验证全部通过
上次报告: docs/commercial-ocr-phase-reports/COCR-M21-commercial-ocr-blocked-credential-missing.md
Handoff: .agent/handoff/COCR-M21-handoff-20260506-115600.md

## 如果用户已提供 credential:

1. 先确认 key 是否存在:
   ```bash
   env | grep -iE '^(BAIDU_|TENCENT_)' | sed 's/=.*/=***/'
   ```

2. 单页 smoke:
   ```bash
   cd /home/carry/project2/pdf-service
   ./.venv/bin/python scripts/run_real_commercial_ocr_smoke.py \
     --pdf '/home/carry/project2/题本/题本篇.pdf' --page 1 \
     --provider baidu_paper_cut_edu --real-smoke true
   ```

3. batch 1/6/16:
   ```bash
   ./.venv/bin/python scripts/run_real_commercial_ocr_batch.py \
     --pdf '/home/carry/project2/题本/题本篇.pdf' --pages '1,6,16' \
     --provider baidu_paper_cut_edu --max-pages 3 --real-smoke true
   ```

4. bbox 对比:
   ```bash
   ./.venv/bin/python scripts/compare_commercial_vs_local_bbox.py \
     'debug/real-commercial-ocr-smoke/current/batch-commercial-ocr-summary.json' \
     'debug/real-data-data-analysis/batch-tiben-selected/batch-ocr-summary.json'
   ```

5. 生成 fixture + workbench E2E:
   ```bash
   export E2E_REAL_BATCH_FIXTURE_ROOT="debug/real-commercial-ocr-smoke/current"
   export E2E_REAL_BATCH_FIXTURE_NAME="batch-commercial-ocr-summary"
   export E2E_REAL_BATCH_EXPECTED_BBOX_SOURCE="baidu_paper_cut_edu"
   cd /home/carry/project2
   pnpm exec playwright test e2e/data-analysis-commercial-ocr-workbench.spec.ts --trace=on
   ```

## 如果 credential 仍缺失:

- 继续不依赖 key 的 P2/P3 增强任务
- 不要重做 M20D/M21 已完成的工作
- 不要伪造 pass

## 不要重复做的事:

- 不要再检查 credential (已全部审计)
- 不要再 retry smoke (没有新 key 会返回相同 key_missing)
- 不要把 tesseract_local_ocr 当商业 OCR
