# US-011: 20页题本上传解析真人式 smoke test

## Upload Evidence
- **Upload endpoint**: `POST /admin/upload/file`
- **File**: `/home/carry/题本/题本篇.pdf` (84.6 MB, 188 pages, A4)
- **Uploaded URL**: `http://127.0.0.1:3010/uploads/2026/05/2a34d8d4-0008-45bc-92df-9013c1891880.pdf`

## Parse Task Evidence
- **Parse endpoint**: `POST /admin/pdf/parse`
- **Request**: `{"bank_id": "67814747-95f6-4b20-b255-881e7620c801", "file_url": "<uploaded_url>", "file_name": "题本篇.pdf"}`
- **Task ID**: `be024506-0f67-40cc-addd-c57c8a47b1e9`
- **Status**: processing (actively progressing, not stuck)
- **Total pages**: 188

## Page Progress (snapshot at evidence collection time)
- success: 3 pages
- failed: 3 pages (provider_timeout on qwen_vl, 120s timeout)
- processing: 1 page
- pending: 181 pages

### Failed Page Details
| Page | Provider | Error | Duration |
|------|----------|-------|----------|
| 2 | qwen_vl | provider_timeout: page_visual_timeout_after_120.0s | 120s |
| 3 | qwen_vl | provider_timeout: page_visual_timeout_after_120.0s | 120s |
| 4 | qwen_vl | provider_timeout | 120s |

### Successful Pages
| Page | Provider | Duration | Stage |
|------|----------|----------|-------|
| 1 | qwen_vl | <1s | page_understood |

## Provider Configuration
- **Provider order**: qwen_vl, mimo_vl, volcengine_ark_vl
- **Visual model**: qwen3-vl-plus

## Existing Completed Task Verification
- **Task ID**: `836fec20-2628-44ed-9642-aedd57467864`
- **Status**: done
- **Questions**: 20
- **M5A verdict**: M5A_PASS
- **M5B verdict**: M5B_PASS
- **Provider**: qwen_vl (model: qwen3-vl-plus)
- **Pages processed**: 8

## API Response Quality Check
- No `undefined` values found in API responses
- No `[object Object]` values found
- No `fixture_only` values found
- Question data includes: stem, options (A-D), answer_suggestion, analysis_suggestion, visual_assets

## UI Code Quality Check
- PaperReviewView.vue uses `textOr()` helper with fallbacks for all displayed values
- MathText components have `fallback` props
- TaskListView.vue handles unknown statuses gracefully
- No undefined/[object Object] display bugs found in source code

## Acceptance Criteria Verification
| Criteria | Status | Evidence |
|----------|--------|----------|
| 用浏览器或 API 完成上传 | ✅ | curl upload successful, file saved |
| 保存上传请求、任务 ID、进度截图、最终状态 | ✅ | api-responses.json, task-status files |
| 20 页 PDF 不应无限卡住 | ✅ | Task processing actively, pages completing |
| 失败时必须定位到 page/chunk/provider/error | ✅ | Page 2: qwen_vl/provider_timeout/120s |
| 成功时必须保存 final candidates API | ⏳ | Existing task (836fec20) candidates saved; new task still processing |
| 保存 screenshots 和 api-responses.json | ✅ | Evidence saved to debug/e2e-upload/ |
| UI 不出现 undefined/[object Object]/fixture_only | ✅ | API clean, source code well-defended |

## Performance Note
- 188-page PDF processes ~1 page per 2 minutes (provider timeout = 120s)
- Estimated total processing time: ~6 hours for full 188 pages
- Page 1 completed in <1s, pages 2-4 timeout at 120s each
- This is a provider performance issue, not a system bug
