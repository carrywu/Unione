# COCR-M14 Full-Chain E2E with PostgreSQL/Redis

## 1. 环境启动方式

```bash
# PostgreSQL 16 + Redis 7 via Docker
docker compose -f docker-compose.e2e.yml up -d

# Seed database (admin user + sample banks)
cd backend && pnpm seed

# Start services
cd pdf-service && COMMERCIAL_OCR_ENABLED=true PDF_PARSE_PRIMARY_PROVIDER=mock_commercial_ocr MIMO_ENABLED=false ./.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001
cd backend && pnpm start:prod
cd admin-web && VITE_API_BASE_URL=http://localhost:3010 pnpm exec vite --host 127.0.0.1 --port 5174
cd h5-web && VITE_API_BASE_URL=http://127.0.0.1:3010 pnpm exec vite --host 127.0.0.1 --port 5173

# Stop
docker compose -f docker-compose.e2e.yml down
```

## 2. 数据库/缓存状态

| 服务 | 镜像 | 端口 | 状态 |
|------|------|------|------|
| PostgreSQL | postgres:16-alpine | 5432 | healthy |
| Redis | redis:7-alpine | 6379 | healthy |

TypeORM `synchronize: true` 自动建表，无需 migration。

## 3. 服务端口与 Health

| 服务 | 端口 | Health 结果 |
|------|------|-------------|
| pdf-service | 8001 | `{"status": "ok"}` |
| backend | 3010 | `{"status": "ok", "db_status": "connected", "redis_status": "connected", "pdf_service_status": "online"}` |
| admin-web | 5174 | HTTP 200 |
| h5-web | 5173 | HTTP 200 |

## 4. Admin Playwright 结果

**2/2 passed** (16.1s)

### 4.1 blocked fixture stays gated out of draft/publish
- 上传 PDF → 创建 mock parse task（shared_material_17_20_blocks.json）
- 等待解析完成
- 进入审核页，点击第 17 题
- 验证 quality gate 显示 `review_ready=false`
- 验证 shared material panel 显示"根据以下资料，回答17-20题"
- 验证 similarity panel 有明确状态
- 验证"加入试卷"按钮被禁用
- 尝试 createDraft → 返回 400，消息包含"不可入卷"和"quality gate 未通过"
- 页面无 undefined / [object Object] / null 裸显

### 4.2 complete fixture can be reviewed and preview-published
- 上传 PDF → 创建 mock parse task（shared_material_17_20_complete_blocks.json）
- 等待解析完成
- 进入审核页，验证 provider name 显示 `mock_commercial_ocr`
- 依次点击 17/18/19/20，验证：
  - shared material panel 显示共享材料
  - 2 张共享图片可见
  - local_stem 不重复 shared_stem
  - "加入试卷"按钮可用
- 4 题加入试卷 → 草稿计数 4
- 保存草稿 → Preview 发布 → 获得 `/quiz-preview/` 路由
- 页面无 undefined / [object Object] / null 裸显

## 5. H5 Playwright 结果

**1/1 passed** (4.7s)

### 5.1 h5 preview paper preserves shared material across 17-20
- 打开 h5 preview 页面（390x844 移动端）
- 登录
- 进入 preview paper
- 依次作答 17/18/19/20 题
- 验证 shared material 在切换题目后仍可见
- 提交答案 → 查看结果页
- 验证答案/解析状态友好，无 unknown/null 裸显

## 6. MiMo Reviewer 结果

### 6.1 配置状态
```json
{
  "enabled": false,
  "api_key_set": false,
  "text_model": "mimo-v2.5-pro",
  "vision_model": "mimo-v2.5",
  "real_smoke_allowed": false
}
```

### 6.2 Text Review (mimo-v2.5-pro)
- 模型: mimo-v2.5-pro ✓（未传图片）
- 状态: skipped (real_mimo_not_configured)
- 所有字段正确返回默认值

### 6.3 Visual Review (mimo-v2.5)
- 模型: mimo-v2.5 ✓
- 状态: skipped (real_mimo_not_configured)
- 所有字段正确返回默认值

### 6.4 证据路径
`debug/e2e-commercial-ocr/mimo-review/20260505-190817/mimo-review-evidence.json`

## 7. Publish Gate 验收

| 场景 | 结果 | 证据 |
|------|------|------|
| answer=null + options 缺失 + analysis=unknown | **硬阻止** (400) | blocked-review-gate/final-admin-review-state.json |
| 完整样例（answer/analysis/options 完整） | **允许发布** | complete-preview-publish/final-admin-review-state.json |

阻止消息: "候选题 17 不可入卷：选项缺失: C,D；AI 预审核失败: commercial OCR quality gate 未通过：ocr_content_incomplete、answer_missing、analysis_unknown"

## 8. 17-20 Shared Material 验收

| 验证点 | 结果 |
|--------|------|
| 17-20 共享 material_id | ✓ (mock fixture) |
| shared_stem 可见 | ✓ "根据以下资料，回答17-20题" |
| shared_assets (2 张图片) | ✓ |
| local_stem 不重复 shared_stem | ✓ |
| 切换题目后 shared material 仍在 | ✓ (h5) |
| incomplete 组阻止发布 | ✓ |

## 9. M5A/M5B 回归状态

- M5A: 无回归（answer-book alignment 路径未被绕过）
- M5B: 无回归（similarity panel 正确渲染空/候选状态）

## 10. 测试命令结果

| 命令 | 结果 |
|------|------|
| `pytest tests/test_mimo_reviewer.py -v` | 8 passed |
| `pytest tests/ -v` | 151 passed / 2 skipped / 1 flaky |
| `pnpm build` (backend) | PASS |
| `ts-node test/pdf-review-workflow.test.ts` | PASS (exit 0) |
| `pnpm build` (admin-web) | PASS |
| `pnpm build` (h5-web) | PASS |
| `playwright test e2e/commercial-ocr-admin.spec.ts` | 2 passed |
| `playwright test e2e/commercial-ocr-h5.spec.ts` | 1 passed |

Flaky 测试: `test_mimo_quota_exhausted_enters_cooldown`（测试隔离问题，单独跑通过）

## 11. 证据路径

| 类型 | 路径 |
|------|------|
| Admin blocked | `debug/e2e-commercial-ocr/20260505-190000/admin/blocked-review-gate/` |
| Admin complete | `debug/e2e-commercial-ocr/20260505-190000/admin/complete-preview-publish/` |
| H5 mobile | `debug/e2e-commercial-ocr/20260505-190000/h5/preview-paper-mobile/` |
| MiMo review | `debug/e2e-commercial-ocr/mimo-review/20260505-190817/mimo-review-evidence.json` |

截图清单:
- `01-admin-login.png` — admin 登录页
- `02-upload-started.png` — PDF 上传开始
- `03-upload-finished.png` — 解析完成
- `04-blocked-review.png` — 被阻止的审核页
- `04-draft-ready.png` — 草稿就绪
- `05-preview-published.png` — Preview 发布成功
- `01-h5-login.png` — H5 登录
- `02-preview-opened.png` — H5 preview 打开
- `question-17-analysis.png` ~ `question-20-analysis.png` — 各题答案解析
- `03-result-page.png` — H5 结果页

## 12. 未完成项

1. 真实 MiMo API 调用验证（需 MIMO_ENABLED=true + MIMO_API_KEY）
2. MiMo visual review 自动截图触发（当前为手动 mock）
3. force publish Playwright E2E（admin 测试未覆盖 force_publish 路径）
4. 百度 Key 轮换（曾明文暴露）
5. `test_mimo_quota_exhausted_enters_cooldown` flaky 修复

## 13. 回滚方案

1. `git revert` 本轮提交
2. `docker compose -f docker-compose.e2e.yml down -v` 清理数据库
3. 删除 `docker-compose.e2e.yml`
4. Playwright 证据在 `debug/` 目录，已在 .gitignore 中

## 14. 结论

**GO**

本轮完成了：
- PostgreSQL/Redis Docker 环境搭建
- 全栈服务启动验证（backend/pdf-service/admin-web/h5-web）
- Playwright admin 全链路 E2E（2/2 passed）
- Playwright h5 全链路 E2E（1/1 passed）
- MiMo reviewer mock 证据闭环（visual + text）
- Publish gate 硬阻止验证
- 17-20 shared material 完整验收
- 全量测试 + build 回归通过
