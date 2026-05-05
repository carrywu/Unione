# COCR-M20A Handoff

## 当前分支

- `mimo`

## 当前 commit

- `e3016fa00cecce3e950ef2a5e58072bde4cf9732`
- 说明: 这是生成本次 handoff 前的已 push 基线；本轮新增的 real smoke / 调度修复提交后，最新 HEAD 以最终 CLI 汇总为准

## baseline tag

- `pre-data-analysis-ocr-api-first-20260505-221735`
- push 状态: 已 push

## 已完成内容

- 资料分析 17-20 OCR API First 闭环仍保持完成态
- post-closure 真实 provider health 已验证：
  - `qwen_vl` pass
  - `volcengine_ark_vl` pass
  - `mimo_vl` fail (`429 quota exhausted`)
- 真实视觉 smoke 已验证：
  - `qwen_vl` 单 provider 跑真实第 5 页会 `180s` 超时失败
  - `volcengine_ark_vl` 单 provider 可解析 shared material 和第 16-20 题，并识别材料不完整
  - `qwen_vl -> volcengine_ark_vl` 顺序可在软超时后成功 hedge
- `pdf-service/ai_client.py` 已补调度修复：
  - 当 `qwen_vl` 为主 provider 且 `volcengine_ark_vl` 在可用列表中时，soft-timeout hedge 优先打到 Ark
  - 该修复专门覆盖仓库当前 `.env` 的 `qwen_vl,mimo_vl,volcengine_ark_vl` 顺序风险
- 真实 `.env` 顺序 smoke 已验证成功：
  - `qwen_vl` 约 `10.8s` 后 soft-timeout
  - `Ark` 接管并成功完成第 5 页解析
  - `mimo_vl` 没有再阻塞这条链路
- 真实文本 smoke 已验证：
  - `qwen-plus` 对真实第 17 题返回 `can_understand_material=false`
  - `can_solve_question=false`
  - `comprehension_confidence=0.25`
  - `needs_human_review=true`
  - 原因与我们预期一致：缺表头、缺单位、缺年份、缺 2019 数据、缺完整地市列表、材料仅显示后半页

## 未完成内容

- 真实 text provider 还没有切进默认产品链路，只做了 smoke
- 真实 visual provider 还没有扩大到更多资料分析样本页
- 非资料分析题型尚未扩展
- 旧 `page_understanding` / `semantic_groups` / `recrop_plan` 还未开始收缩
- Ark endpoint `ep-20260504082005-gvl4b` 对 responses API 仍返回 `403 AccessDenied`，当前成功依赖模型名 fallback `doubao-seed-2-0-lite-260215`

## 测试结果

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_commercial_ocr_quality_gate.py tests/test_commercial_ocr_visual_understanding.py tests/test_commercial_ocr_semantic_assembler.py -q`: `21 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_ai_client_page_visual_fallbacks.py -q`: `19 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_ai_client_page_visual_fallbacks.py -q`: `27 passed`
- `cd backend && node --require ts-node/register --require tsconfig-paths/register test/pdf-review-workflow.test.ts`: PASS
- `cd backend && pnpm build`: PASS
- `cd admin-web && pnpm build`: PASS
- `cd h5-web && pnpm build`: PASS
- `pnpm exec playwright test e2e/ --trace=on`: `9 passed`
- `cd backend && pnpm test`: skipped，原因是 `backend/package.json` 无 `test` script
- `cd pdf-service && ./.venv/bin/python tools/provider_health_report.py`: PASS（本地产物含 provider 响应预览，未纳入 commit）
- `cd pdf-service && ./.venv/bin/python tools/visual_api_smoke.py ... --pages 4-5 ...`: 
  - `qwen-only` fail
  - `ark-only` pass
  - `qwen->ark` pass
  - current env order pass after hedge fix

## Playwright 证据路径

- `debug/e2e-commercial-ocr/2026-05-05T15-03-11-354Z/`
- `test-results/`

## 真实 smoke 证据路径

- `debug/real-provider-smoke/20260505-real-smoke/qwen-page5/`
- `debug/real-provider-smoke/20260505-real-smoke/ark-page5/`
- `debug/real-provider-smoke/20260505-real-smoke/qwen-ark-page5/`
- `debug/real-provider-smoke/20260505-real-smoke/env-order-page5/`
- `.agent/reports/data-analysis-q17-qwen-text-smoke.md`

## 服务启动/停止命令

```bash
# E2E 栈启动
bash -lc './scripts/e2e/start-commercial-ocr-stack.sh; while true; do sleep 3600; done'

# Playwright
pnpm exec playwright test e2e/ --trace=on

# 停止
./scripts/e2e/stop-commercial-ocr-stack.sh

# provider health
cd pdf-service && ./.venv/bin/python tools/provider_health_report.py

# 真实视觉 smoke
cd pdf-service && ./.venv/bin/python tools/visual_api_smoke.py /home/carry/project2/pdf-service/题本篇.pdf --pages 4-5 --output-dir /home/carry/project2/debug/real-provider-smoke/<label> --clean-output --refresh-cache
```

## 报告路径

- `docs/commercial-ocr-phase-reports/COCR-M20A-data-analysis-first.md`
- `.agent/reports/data-analysis-first-ocr-api-understanding-report.md`
- `.agent/reports/data-analysis-q17-qwen-text-smoke.md`

## 下一轮 resume prompt

继续在 `/home/carry/project2` 的 `mimo` 分支推进 COCR。保持 OCR API First，不扩全题型。优先把真实 smoke 从第 5 页扩大到更多资料分析页，验证 Ark fallback 是否稳定、qwen timeout 是否可通过更小图或 prompt 控制改善。不要把 MiMo 拉回第一备援。真实 text provider 仍先停留在 smoke 层，只有当更多样本页都能稳定拒答/解题后，再评估切入默认资料分析 understanding 链。
