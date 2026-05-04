# US-012: 答本上传与 M5A 真实对撞验证

## Answer Book Upload
- **File**: `/home/carry/答本/解析篇.pdf`
- **Upload URL**: `http://127.0.0.1:3010/uploads/2026/05/92b21c0c-d66e-40ed-b84c-09e50be2fb85.pdf`
- **Endpoint**: `POST /admin/upload/file`

## Task 836fec20 M5A Verification

### Acceptance Criteria Results
| Criteria | Status | Evidence |
|----------|--------|----------|
| 使用 `/home/carry/答本/解析篇.pdf` | ✅ | answer_book_path in M5A report |
| 对已有任务 836fec20 验证 | ✅ | paper-candidates API verified |
| M5A 字段包含 matched/conflict | ✅ | verdict field: "matched" (6) / "conflict" (14) |
| M5A 字段包含 match_confidence | ✅ | match_confidence: 1 for all 20 |
| M5A 字段包含 evidence | ✅ | evidence array present for all 20 |
| M5A 字段包含 matched_answer_item_id | ✅ | present for 20/20 questions |
| 不出现 BLOCKED_BY_MISSING_ANSWER_BOOK | ✅ | 0 blocked |
| 不出现 fixture_only | ✅ | 0 fixture_only |
| 20/20 有答本结果 | ✅ | 20/20 have answer_from_answer_book |
| conflict 只提示人工复核 | ✅ | 14/14 conflicts have needs_human_review=true |
| backend 测试通过 | ✅ | EXIT: 0 |

### M5A Summary
- **Verdict**: M5A_PASS
- **Total questions**: 20
- **Matched**: 6 (questions 14, 16, 17, 18, 19, 20)
- **Conflict**: 14 (all have needs_human_review=true)
- **Match method**: normalized_stem_similarity
- **Answer book**: `/home/carry/答本/解析篇.pdf`

### M5A Data Structure (per question)
```
m5_answer_book:
  verdict: "matched" | "conflict"
  status: "matched" | "conflict"
  match_confidence: 1
  match_method: "normalized_stem_similarity"
  evidence: [...]
  matched_answer_item_id: "answer-item-pXX-qYY"
  answer_from_answer_book: "A"|"B"|"C"|"D"
  analysis_from_answer_book: "..."
  needs_human_review: true|false
  fixture_only: false
```

### Answer Book Evidence (per M5A report)
- question_book_pdf: /home/carry/题本/题本篇.pdf
- answer_book_pdf: /home/carry/答本/解析篇.pdf
- answer_book_page: (varies per question)
- answer_item_source: vision_page_extraction

## New Task be024506 Status
- Task is still processing (4/188 pages complete)
- M5A matching will occur after PDF parsing completes
- Answer book uploaded and available for matching

## Quality Checks
- backend build: PASS
- admin-web build: PASS
- backend test: PASS (EXIT 0)
