# Commercial OCR Full-Chain E2E Handoff

## 当前分支

- `main`

## 当前代码基线 commit

- `864ff7d`

## 已完成内容

- backend commercial OCR DTO / review / publish gate wiring
- pdf-service visual understanding mock integration
- admin review UI provider/material/quality gate/similarity display
- h5 shared-material preview rendering for 17-20
- root Playwright admin + h5 full-chain E2E
- provider health / visual smoke retry known regressions cleanup
- phase reports / PRD / progress append

## 未完成内容

- 真实 VLM visual understanding 接入与成本控制
- 真实 Tencent/Baidu single-page smoke hardening
- backend 独立 `/api/health` 探针
- warning case 人工强制放行策略产品化

## 测试结果

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_commercial_ocr_kernel_integration.py -v`
  - `10 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_semantic_assembler.py tests/test_commercial_ocr_quality_gate.py tests/test_tencent_ocr_provider.py tests/test_commercial_ocr_visual_understanding.py -v`
  - `16 passed / 1 skipped`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/ -v`
  - `144 passed / 2 skipped`
- `cd backend && pnpm build`
  - passed
- `cd backend && pnpm exec ts-node -r tsconfig-paths/register test/pdf-review-workflow.test.ts`
  - passed
- `cd admin-web && pnpm build`
  - passed
- `cd h5-web && pnpm build`
  - passed
- `pnpm exec playwright test e2e/commercial-ocr-admin.spec.ts`
  - `2 passed`
- `pnpm exec playwright test e2e/commercial-ocr-h5.spec.ts`
  - `1 passed`

## Playwright 证据路径

- `debug/e2e-commercial-ocr/20260505-014457/admin/blocked-review-gate/`
- `debug/e2e-commercial-ocr/20260505-014457/admin/complete-preview-publish/`
- `debug/e2e-commercial-ocr/20260505-014457/h5/preview-paper-mobile/`

## 服务启动命令

```bash
cd /home/carry/project2/pdf-service && ./.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001
cd /home/carry/project2/backend && pnpm start:prod
cd /home/carry/project2/admin-web && pnpm exec vite --host 127.0.0.1 --port 5174
cd /home/carry/project2/h5-web && pnpm exec vite --host 127.0.0.1 --port 5173
```

## 数据清理命令

```bash
TOKEN=$(curl -s http://127.0.0.1:3010/api/auth/login -H 'Content-Type: application/json' -d '{"phone":"admin","password":"admin"}' | jq -r '.data.access_token')
for TASK_ID in 6331163e-dbc4-437f-857d-08be741a53fc 486608aa-47be-4900-afbd-206a342a2593 1e791907-53ab-4391-93c2-677fb1821c56; do
  curl -s -X DELETE "http://127.0.0.1:3010/api/admin/pdf/task/${TASK_ID}" -H "Authorization: Bearer ${TOKEN}" >/dev/null
done
rm -f /home/carry/project2/debug/paper-drafts/61f4c4b7-ff26-4119-97d4-d0911fe38738.json
rm -f /home/carry/project2/debug/m6-preview-papers/61f4c4b7-ff26-4119-97d4-d0911fe38738.json
rm -f /home/carry/project2/debug/paper-drafts/9d860d11-6b90-42e0-80d0-848a642342b3.json
rm -f /home/carry/project2/debug/m6-preview-papers/9d860d11-6b90-42e0-80d0-848a642342b3.json
rm -rf /home/carry/project2/debug/e2e-commercial-ocr/20260505-014457
```

## 下一步命令

```bash
git checkout main
git pull --ff-only origin main
cd /home/carry/project2/pdf-service && ./.venv/bin/python scripts/eval_commercial_ocr.py
cd /home/carry/project2 && E2E_USE_MOCK_OCR=true pnpm exec playwright test e2e/commercial-ocr-admin.spec.ts e2e/commercial-ocr-h5.spec.ts
```

## resume prompt

继续在 `/home/carry/project2` 的 `main` 分支推进 commercial OCR 主线。当前 code baseline 为 `864ff7d`，mock commercial OCR -> semantic assembler -> visual understanding mock -> quality gate -> admin preview publish -> h5 preview 已全链路验证通过，`pdf-service` 全量 pytest 为 `144 passed / 2 skipped`。下一步优先做真实 VLM selected-case hardening、真实 Tencent/Baidu single-page smoke、backend `/api/health`、以及 warning case 人工强制放行策略。默认不要调用真实腾讯/百度 API；对话里曾明文暴露百度 Key，必须继续提醒轮换。
