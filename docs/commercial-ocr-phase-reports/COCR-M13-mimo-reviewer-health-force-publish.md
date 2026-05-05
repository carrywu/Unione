# COCR-M13 MiMo Reviewer Integration + Backend Health + Force Publish

## 1. 本阶段目标

1. 接入 MiMo 视觉/文本评审真实调用能力（默认 mock，真实调用需配置）
2. 新增 backend 公开 `/api/health` 健康探针
3. 实现 warning case 人工强制放行策略（force_publish）

## 2. 修改范围

### 2.1 MiMo Reviewer
- 新增 `pdf-service/commercial_ocr/mimo_reviewer.py`
- 新增 `pdf-service/tests/test_mimo_reviewer.py`（8 tests）
- 更新 `pdf-service/commercial_ocr/service.py`（集成 MiMo text review）
- 更新 `pdf-service/commercial_ocr/types.py`（新增 `mimo_text_review` 字段）
- 更新 `pdf-service/.env.example`（MiMo reviewer 环境变量）

### 2.2 Backend Health
- 新增 `backend/src/modules/system/health.controller.ts`
- 更新 `backend/src/modules/system/system.module.ts`

### 2.3 Force Publish
- 更新 `backend/src/modules/pdf/dto/publish-result.dto.ts`（新增 `force_publish`, `force_reason`）
- 更新 `backend/src/modules/pdf/pdf.service.ts`（新增 `isForcePublishable` 方法 + force publish 逻辑）

## 3. 架构/API 变化

### 3.1 MiMo Reviewer

`mimo_reviewer.py` 提供两个核心函数：

- `review_visual_screenshot()` — 调用 `mimo-v2.5`（视觉模型）评审截图
- `review_text_payload()` — 调用 `mimo-v2.5-pro`（文本模型）评审 JSON payload

默认行为：
- `MIMO_ENABLED=false` → 返回 `skipped` mock 结果
- `MIMO_ENABLED=true` 但 `MIMO_API_KEY` 缺失 → 返回 `skipped`
- 真实调用失败/429/timeout → 自动降级为 `skipped`，不阻塞主流程

环境变量：
```bash
MIMO_ENABLED=false
MIMO_API_KEY=
MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
MIMO_TEXT_MODEL=mimo-v2.5-pro
MIMO_VISION_MODEL=mimo-v2.5
MIMO_TIMEOUT_MS=120000
```

`CommercialOCRExecution` 新增字段：
- `mimo_text_review: dict | None` — MiMo 文本评审结果
- `mimo_reviewer_status: dict` — MiMo reviewer 配置状态（在 execution_summary 中）

### 3.2 Backend Health

`GET /api/health` — 无需认证，返回：
```json
{
  "status": "ok|degraded",
  "timestamp": "...",
  "node_version": "...",
  "uptime_seconds": N,
  "memory_used_mb": N,
  "db_status": "connected|error",
  "redis_status": "connected|error",
  "pdf_service_status": "online|offline",
  "env": "development|production"
}
```

### 3.3 Force Publish

`POST /admin/pdf/publish-result/:taskId` 新增参数：
- `force_publish: boolean` — 强制发布 warning 级别题目
- `force_reason: string` — 强制发布理由（force_publish=true 时必填）

`isForcePublishable` 仍然硬阻止：
- `answer=null` → 拒绝
- `layout-only OCR` → 拒绝
- `extracted_but_incomplete=true` → 拒绝

允许通过（with force）：
- `needs_review=true`
- `parse_warnings` 存在
- `fallback_used=true`
- `analysis=unknown`
- quality gate warnings

返回值新增：
- `force_published: boolean`
- `force_reason: string | undefined`

## 4. 测试与验证

```bash
# MiMo reviewer tests (8 passed)
cd pdf-service && ./.venv/bin/python -m pytest tests/test_mimo_reviewer.py -v

# Full pdf-service suite
cd pdf-service && ./.venv/bin/python -m pytest tests/ -v
# 151 passed, 2 skipped, 1 flaky (test_mimo_quota_exhausted_enters_cooldown - test isolation issue, passes in isolation)

# Backend build
cd backend && pnpm build  # PASS

# Backend test
cd backend && pnpm exec ts-node -r tsconfig-paths/register test/pdf-review-workflow.test.ts  # PASS (exit 0)

# Admin-web build
cd admin-web && pnpm build  # PASS

# H5-web build
cd h5-web && pnpm build  # PASS
```

## 5. Playwright/MiMo 证据路径

Playwright E2E 本轮未执行（MySQL/Redis 不可用）。
历史证据路径：`debug/e2e-commercial-ocr/20260505-014457/`

## 6. 风险与遗留问题

1. MiMo reviewer 真实调用需要 `MIMO_ENABLED=true` + `MIMO_API_KEY`，当前默认 mock
2. MiMo visual review 需要图片 base64 输入，当前未在 pipeline 中自动触发（需要页面截图能力）
3. `test_mimo_quota_exhausted_enters_cooldown` 在全量测试中偶尔失败（测试隔离问题，单独跑通过）
4. Playwright E2E 需要 MySQL/Redis 运行环境
5. **百度 Key 曾在对话中明文暴露，必须继续提醒轮换**

## 7. 回滚方案

1. `git revert` 本阶段提交
2. MiMo reviewer 文件删除不影响现有功能（mock fallback 机制）
3. Force publish 为新增功能，删除后回退到原有严格 gate
4. Health controller 删除后不影响业务

## 8. 结论

`GO_WITH_RISK`

本轮新增了 MiMo reviewer 真实调用能力、backend health 探针和 force publish 策略。
所有测试通过（除 1 个已知 flaky 测试），所有 build 通过。
需要在有 MySQL/Redis 的环境中验证 Playwright E2E。
