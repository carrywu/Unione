# COCR-M21 Blocked Report

## Status: BLOCKED / credential_missing

- branch: `mimo`
- commit: `5be7193`
- date: `2026-05-06 11:56 CST`
- route: C (credential still missing, identical to M20D)

## Key Finding

All credential sources checked — shell env, root/backend/pdf-service `.env`, alternative `.env.local`/`.env.commercial`/`.agent/env` — contain **zero** Baidu or Tencent commercial OCR keys. Backend DB config source unreachable (MySQL ECONNREFUSED). Situation unchanged from M20D.

## Missing Variables

- `BAIDU_API_KEY` / `BAIDU_SECRET_KEY` (百度 OCR)
- `TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY` (腾讯 OCR)

## What Was Done Instead

1. Committed a checkpoint fix: `provider_issue_reason` now correctly returns `None` when provider status is `ok`/`partial`/`ok_local_fallback` (was returning misleading `skipped_reason`)
2. All baseline validations pass: 17 pytest, tsc, build, script syntax
3. Generated env-diagnosis, debug artifacts, phase report

## Verified Scripts Ready for Credential Injection

- `pdf-service/scripts/run_real_commercial_ocr_smoke.py` — single-page smoke
- `pdf-service/scripts/run_real_commercial_ocr_batch.py` — batch 1/6/16
- `pdf-service/scripts/compare_commercial_vs_local_bbox.py` — bbox comparison
- `pdf-service/scripts/provider_health_report.py` — health report
- `scripts/e2e/start-commercial-ocr-stack.sh` — E2E stack (fixed to honor real env)
- `admin-web/e2e/data-analysis-commercial-ocr-workbench.spec.ts` — Playwright spec

## Next Step After Key Injection

```bash
cd /home/carry/project2/pdf-service
./.venv/bin/python scripts/run_real_commercial_ocr_smoke.py \
  --pdf '/home/carry/project2/题本/题本篇.pdf' --page 1 \
  --provider baidu_paper_cut_edu --real-smoke true
```
