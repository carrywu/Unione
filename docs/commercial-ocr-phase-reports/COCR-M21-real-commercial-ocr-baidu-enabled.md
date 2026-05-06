# COCR-M21: Real Commercial OCR — Baidu Enabled

## Status: PASS ✅

- **Branch**: `mimo`
- **Commit**: `0453d902c88bd5d919f852f0b3af84cdeecac592`
- **Date**: 2026-05-06 16:40 CST
- **Route**: A (credential available, real commercial OCR enabled)

## Summary

百度 OCR 商业主链已成功跑通。真实 credential 已注入，单页 smoke、批量 smoke、bbox 对比全部通过。腾讯 OCR 仍缺少 SecretKey，待补充。

## Credential Status

| Provider | Variable | Status |
|----------|----------|--------|
| Baidu OCR | `BAIDU_API_KEY` | ✅ Set (masked: `8cv***pi0v`) |
| Baidu OCR | `BAIDU_SECRET_KEY` | ✅ Set (masked: `371***stY`) |
| Tencent OCR | `TENCENT_SECRET_ID` | ✅ Set (masked: `AKI***Jj9`) |
| Tencent OCR | `TENCENT_SECRET_KEY` | ❌ Missing |

## Test Results

### ✅ Single Page Smoke (Page 1)
```
Provider: baidu_paper_cut_edu
Status: ok
Latency: 1381ms
Question count: 5
Bbox count: 5
```

### ✅ Batch Smoke (Pages 1, 6, 16)
```
Provider: baidu_paper_cut_edu
Commercial success: 3/3 pages
Blocked: 0 pages
Page 1: 5 questions, 5 bboxes
Page 6: 4 questions, 4 bboxes
Page 16: 7 questions, 7 bboxes
```

### ✅ Commercial vs Local Bbox Comparison
```
All pages recommend: commercial (baidu_paper_cut_edu)
Commercial bbox_count > 0 on all pages
Local bbox_count = 0 on all pages (no local fallback used)
```

### ✅ PDF Service Tests
```
37 passed, 1 skipped, 126 deselected
```

### ✅ Admin Web TypeScript
```
pnpm exec tsc --noEmit: PASS
```

### ✅ Admin Web Build
```
pnpm build: PASS (built in 7.50s)
```

### ⚠️ Workbench E2E
```
Status: BLOCKED (backend service not running)
Error: connect ECONNREFUSED 127.0.0.1:3010
Action needed: Start backend service before running E2E
```

## Key Findings

1. **百度 OCR 真实可用**：所有页面都成功返回了 bbox 数据，延迟在 1.3-1.4 秒范围内。
2. **bbox_source 已切换**：从 `tesseract_local_ocr` 切换到 `baidu_paper_cut_edu`。
3. **无 fallback 使用**：商业 OCR 直接成功，未触发本地 OCR fallback。
4. **腾讯 OCR 待补充**：缺少 `TENCENT_SECRET_KEY`，无法测试腾讯 provider。

## Debug Artifacts

- `debug/real-commercial-ocr-smoke/20260506-163311/` — single page smoke
- `debug/real-commercial-ocr-smoke/20260506-163331/` — batch smoke (pages 1, 6, 16)
- `debug/real-commercial-ocr-smoke/20260506-163643/` — bbox comparison
- `debug/real-commercial-ocr-smoke/current/` — symlink to latest

## Next Steps

### P0: Complete M21
1. ✅ 百度 OCR 单页 smoke
2. ✅ 百度 OCR 批量 smoke
3. ✅ bbox 对比
4. ⏸️ Workbench E2E (need backend service)
5. ⏸️ VLM/LLM 复验 (need backend service)

### P1: M22 Preparation
1. 在真实 commercial bbox 下重跑 VLM/LLM 预审核
2. 生成 page-understanding.json
3. 生成 semantic-groups.json
4. 生成 ai-audit-results.json

### P2: Tencent OCR
1. 补充 `TENCENT_SECRET_KEY`
2. 运行腾讯 OCR 单页 smoke
3. 运行腾讯 OCR 批量 smoke
4. 运行 bbox 对比

## Resume Command

```bash
# Start backend service first
cd /home/carry/project2
pnpm run start:dev  # or equivalent backend start command

# Then run workbench E2E
cd admin-web
E2E_REAL_BATCH_FIXTURE_ROOT="/home/carry/project2/debug/real-commercial-ocr-smoke/current" \
E2E_REAL_BATCH_FIXTURE_NAME="batch-commercial-ocr-summary" \
E2E_REAL_BATCH_EXPECTED_BBOX_SOURCE="baidu_paper_cut_edu" \
pnpm exec playwright test e2e/data-analysis-commercial-ocr-workbench.spec.ts --trace=on
```

## Resume Prompt

```markdown
# COCR-M21 Resume Prompt

## Current State
- Branch: mimo
- Commit: 0453d902c88bd5d919f852f0b3af84cdeecac592
- Status: Baidu OCR PASS, Workbench E2E BLOCKED (no backend)

## Completed
- Baidu OCR single page smoke: PASS
- Baidu OCR batch smoke (1,6,16): PASS
- Bbox comparison: PASS
- PDF service tests: 37 passed
- Admin web tsc: PASS
- Admin web build: PASS

## Blocked
- Workbench E2E: needs backend service running
- VLM/LLM audit: needs backend service running
- Tencent OCR: needs TENCENT_SECRET_KEY

## Next Steps
1. Start backend service
2. Run workbench E2E with real commercial fixture
3. Run VLM/LLM audit with real commercial bbox
4. If Tencent key available, run Tencent OCR smoke
```
