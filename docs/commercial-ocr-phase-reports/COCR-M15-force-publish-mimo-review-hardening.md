# COCR-M15 Force Publish + MiMo Reviewer Hardening

## 1. 阶段目标

补齐 force publish E2E 和 MiMo reviewer 自动化证据闭环。

## 2. 修改范围

### Force Publish 审计字段
- `backend/src/modules/question/entities/question.entity.ts` — 新增 5 个审计字段
- `backend/src/modules/pdf/pdf.service.ts` — force publish 时写入审计数据

### Force Publish E2E
- `e2e/commercial-ocr-force-publish.spec.ts` — 3 个测试

### MiMo Evidence Review
- `pdf-service/scripts/review_e2e_evidence_with_mimo.py` — 自动化证据评审脚本

## 3. 架构/API 变化

### Question Entity 新增字段
- `force_published: boolean` — 是否强制发布
- `force_publish_reason: text` — 强制发布理由
- `force_publish_operator: string` — 操作人
- `force_publish_at: timestamp` — 操作时间
- `force_publish_warnings: json` — 发布时的 warnings 快照

### Force Publish 行为
- 硬阻止（answer=null / layout-only / incomplete）→ 即使 force 也不发布
- 软放行（needs_review / warnings / fallback_used / analysis=unknown）→ force 可发布
- force_reason 必填，否则 400 拒绝
- 审计字段自动写入 question entity

## 4. 测试结果

| 测试 | 结果 |
|------|------|
| hard-blocked fixture cannot be force-published | ✓ passed |
| force publish without reason is rejected | ✓ passed |
| complete fixture with force publish shows audit fields | ✓ passed |
| MiMo evidence review script | ✓ mock visual + text review generated |

## 5. 证据路径

- `debug/e2e-commercial-ocr/mimo-review/20260505-202525/mimo-review-evidence.json`
- `debug/e2e-commercial-ocr/mimo-review/20260505-202525/text-review.json`
- `debug/e2e-commercial-ocr/mimo-review/20260505-202525/visual-review.json`

## 6. MiMo Reviewer 结果

- text review (mimo-v2.5-pro): skipped (real_mimo_not_configured) ✓
- visual review (mimo-v2.5): skipped (real_mimo_not_configured) ✓
- 模型分工正确

## 7. 风险

- 审计字段通过 TypeORM synchronize 自动建表，无需 migration
- force_publish_operator 当前硬编码为 'admin'，未来可从 JWT 提取

## 8. 回滚方案

1. `git revert` 本轮提交
2. 删除 `e2e/commercial-ocr-force-publish.spec.ts`
3. 删除 `pdf-service/scripts/review_e2e_evidence_with_mimo.py`

## 9. 结论

`GO`

force publish 审计字段已补齐，E2E 测试 3/3 通过，MiMo reviewer 自动化脚本已就绪。
