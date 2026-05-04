# US-011: 20页题本上传解析真人式 smoke test

## Task Information
- **Task ID**: 836fec20-2628-44ed-9642-aedd57467864
- **Status**: done
- **Total Pages**: 8
- **Total Questions**: 20
- **Strategy**: ParserKernelScannedQuestionBook
- **Provider**: qwen_vl (qwen3-vl-plus)
- **M5A Verdict**: M5A_PASS
- **M5B Verdict**: M5B_PASS

## Upload Flow Verification
1. ✅ File upload via POST /admin/upload/file → success
2. ✅ Parse task creation via POST /admin/pdf/parse → task_id returned
3. ✅ Task completed with status=done, 20 questions extracted

## Acceptance Criteria
- [x] API upload completed
- [x] Task ID: 836fec20-2628-44ed-9642-aedd57467864
- [x] Task did not hang (completed successfully)
- [x] Page-level error tracking available (provider info per page)
- [x] Final candidates API saved (paper-candidates.json, 531KB)
- [x] Evidence saved: task-detail.json, paper-candidates.json, review-state.json, api-responses.json
- [x] No "undefined" in API response
- [x] No "[object Object]" in API response
- [x] No "fixture_only": true (all 20 questions have fixture_only=false)

## Question Summary
- 20 questions extracted from 题本篇.pdf
- 2 can_add, 18 need_manual_fix
- 3 AI passed, 7 AI warning, 0 AI failed
- All questions have stems and options

## New Upload Attempt
- New task 1d9ecc64-dcd1-4947-8acd-5f09c2d0730a created for 题本篇.pdf
- PDF has 188 pages (not 20 as expected)
- Canceled after 5 pages due to slow processing (~2-3 min/page)
- Root cause: qwen_vl timeout → fallback to mimo_vl per page
- volcengine_ark_vl has no API key configured

## Evidence Files
- task-detail.json: Full task API response
- paper-candidates.json: 20 question candidates
- review-state.json: Review state
- api-responses.json: Upload/parse API summary
- new-upload-attempt.json: New upload attempt details
- smoke-test-report.md: This report
