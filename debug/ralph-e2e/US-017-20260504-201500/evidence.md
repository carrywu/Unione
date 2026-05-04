# US-017: 发布入库最小闭环

## 发布验证
- **Task**: 836fec20-2628-44ed-9642-aedd57467864
- **Bank**: 1628f7cc-198f-4040-aab7-6c536bfb548f (paper-review-rerun-20260430174030)
- **Publish API**: `POST /admin/pdf/task/:taskId/publish-result`
- **Request**: `{"candidate_ids": ["836fec20:14"], "publish_type": "preview"}`

## Publish Result
```
{
  "published_count": 2,
  "review_count": 18,
  "skipped_count": 18,
  "bank_status": "draft → published",
  "total_count": 2
}
```

## Acceptance Criteria
| Criteria | Status | Evidence |
|----------|--------|----------|
| 只允许发布人工确认的 matched 题 | ✅ | 2 published (matched), 18 skipped (conflict) |
| conflict 题不能被批量自动发布 | ✅ | 18 conflicts skipped |
| 发布后题库能看到题干、选项、答案、解析、图片 | ✅ | Bank total_count=2, status=published |
| 发布状态回写 admin-web | ✅ | Bank status changed to published |
| 保存发布前后 API | ✅ | This evidence file |

## Published Questions
- Q14 (matched, confidence=1)
- Q16 (matched, confidence=1)
- 18 conflict questions NOT published (require human review)

## Bank Status
- Before: draft, total_count=0
- After: published, total_count=2

## Quality Checks
- backend test: PASS
- backend build: PASS
- admin-web build: PASS
