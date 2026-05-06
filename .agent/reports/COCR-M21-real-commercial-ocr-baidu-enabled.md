# COCR-M21: Real Commercial OCR — Baidu Enabled

## Status: PARTIAL PASS ✅⚠️

- **Branch**: mimo
- **Commit**: 0453d902c88bd5d919f852f0b3af84cdeecac592
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
Question numbers: [1, 2, 3, 4, 5]
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

## Reports Generated

- `docs/commercial-ocr-phase-reports/COCR-M21-real-commercial-ocr-baidu-enabled.md`
- `.agent/handoff/COCR-M21-handoff-20260506-164000.md`
- `.agent/handoff/COCR-M21-resume-prompt-20260506-164000.md`

## Next Steps (Priority Order)

1. **Start backend service** and run workbench E2E
2. **Run VLM/LLM audit** with real commercial bbox
3. **If Tencent key available**, run Tencent OCR smoke tests
4. **Begin M22** semantic understanding and AI audit

## Resume Command

```bash
# Start backend first
cd /home/carry/project2
pnpm run start:dev  # or equivalent

# Then run workbench E2E
cd admin-web
E2E_REAL_BATCH_FIXTURE_ROOT="/home/carry/project2/debug/real-commercial-ocr-smoke/current" \
E2E_REAL_BATCH_FIXTURE_NAME="batch-commercial-ocr-summary" \
E2E_REAL_BATCH_EXPECTED_BBOX_SOURCE="baidu_paper_cut_edu" \
pnpm exec playwright test e2e/data-analysis-commercial-ocr-workbench.spec.ts --trace=on
```

## Git Status

- **Branch**: mimo
- **Commit**: 0453d902c88bd5d919f852f0b3af84cdeecac592
- **Working tree**: Clean (no uncommitted changes)
- **Push**: Not pushed (no new commits)

## Notes

1. **腾讯 OCR SecretKey 缺失**：用户提供了 `TENCENT_SECRET_ID`，但 `TENCENT_SECRET_KEY` 为空。需要补充后才能测试腾讯 provider。
2. **Workbench E2E 阻塞**：需要启动后端服务才能运行 E2E 测试。建议在下一个 session 中先启动后端服务。
3. **VLM/LLM 复验阻塞**：同样需要后端服务运行。
4. **无 mock 使用**：所有测试都使用真实商业 OCR credential，未使用 mock provider。
5. **无 tesseract_local_ocr 冒充**：bbox_source 明确为 `baidu_paper_cut_edu`，未伪装。
