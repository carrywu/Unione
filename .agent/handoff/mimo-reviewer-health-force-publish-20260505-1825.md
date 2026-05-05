# MiMo Commercial OCR Handoff

## 当前分支

- `mimo`

## 当前代码基线 commit

- `7def800` (之前的最新提交)
- 本轮新增改动尚未提交

## 本轮完成内容

1. **backend `/api/health` 公开探针**
   - 无需认证，返回 db/redis/pdf-service 状态
   - 文件: `backend/src/modules/system/health.controller.ts`

2. **MiMo reviewer 真实调用能力**
   - `mimo-v2.5` 视觉评审（截图/图片）
   - `mimo-v2.5-pro` 文本评审（JSON payload）
   - 默认 mock，真实调用需 `MIMO_ENABLED=true` + `MIMO_API_KEY`
   - 失败自动降级为 skipped，不阻塞主流程
   - 文件: `pdf-service/commercial_ocr/mimo_reviewer.py`

3. **MiMo text review 集成到 pipeline**
   - `CommercialOCRExecution` 新增 `mimo_text_review` 字段
   - `execution_summary` 新增 `mimo_reviewer_status`
   - 文件: `pdf-service/commercial_ocr/service.py`, `types.py`

4. **warning case 人工强制放行策略**
   - `force_publish` + `force_reason` 参数
   - 硬阻止: answer=null, layout-only, incomplete material group
   - 软放行: needs_review, warnings, fallback_used, analysis=unknown
   - 文件: `backend/src/modules/pdf/dto/publish-result.dto.ts`, `pdf.service.ts`

5. **MiMo reviewer 测试** (8 tests)
   - 文件: `pdf-service/tests/test_mimo_reviewer.py`

6. **阶段报告**
   - 文件: `docs/commercial-ocr-phase-reports/COCR-M13-mimo-reviewer-health-force-publish.md`

## 未完成内容

- Playwright E2E 全链路复验（需 MySQL/Redis 环境）
- MiMo visual review 自动触发（需页面截图能力）
- 真实 MiMo API 调用验证（需 MIMO_API_KEY）
- 百度 Key 轮换

## 测试结果

- `pdf-service` 全量: `151 passed / 2 skipped / 1 flaky`
- `backend build`: PASS
- `backend test`: PASS (exit 0)
- `admin-web build`: PASS
- `h5-web build`: PASS

## 下一步建议

1. 在有 MySQL/Redis 的环境中运行 Playwright E2E
2. 配置真实 MiMo API Key 验证 visual/text review
3. MiMo visual review 自动截图触发集成
4. 百度 Key 轮换
5. 合并回 main

## resume prompt

继续在 `/home/carry/project2` 的 `mimo` 分支推进。本轮新增了 MiMo reviewer 真实调用能力、backend `/api/health` 探针、force publish 策略。pdf-service 全量测试 151 passed / 2 skipped。下一步优先在有 MySQL/Redis 的环境中跑 Playwright E2E，验证 force publish 和 MiMo reviewer 集成效果。默认不消耗真实 MiMo 额度。百度 Key 曾明文暴露，必须继续提醒轮换。
