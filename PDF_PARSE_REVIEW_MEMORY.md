# PDF Parse And Review Memory

## Current User Stop Point

- User said `停`, then asked `生成记忆文档`.
- Do not continue implementation automatically from the previous admin demo validation.
- This document is the handoff memory for the next session.

## Project Context

- Workspace: `/Users/apple/Downloads/公考/project2`
- Repo contains:
  - `h5-web`
  - `admin-web`
  - `backend`
  - `pdf-service`
- Goal has shifted from demo validation to fixing the real PDF parsing and admin review workflow for data-analysis question books.

## Services And Accounts

- `admin-web`: `http://127.0.0.1:5173`
- `h5-web`: `http://127.0.0.1:5174`
- `backend`: `http://127.0.0.1:3010`
- `pdf-service`: `http://127.0.0.1:8001`
- Admin login:
  - phone: `13800138000`
  - password: `123456`

## Work Completed So Far

- Added backend `POST /admin/pdf/task/:taskId/publish-result`.
- Added backend `GET /admin/banks/:id/export-json`.
- Added admin-web `pdf/tasks` operation button for one-click publishing parse results.
- Added backend local upload provider:
  - `UPLOAD_PROVIDER=local`
  - files stored under `backend/uploads/`
  - static access through `/uploads/*`
- Created `MVP_LOCAL_RUNBOOK.md`.
- Updated example API base URLs to `http://127.0.0.1:3010` in frontend env examples.
- Verified local service health earlier:
  - `pdf-service /health` returned `200`
  - `backend /api/banks?page=1&pageSize=1` returned `200`
  - `admin-web` returned `200`
  - `h5-web` returned `200`

## Real Sample Inventory

### Question Books

- `题本/题本篇.pdf`: 188 pages, first pages text-empty/scanned style.
- `题本/最新：1200题题本.pdf`: 304 pages, first pages text-empty/scanned style.
- `题本/2026资料分析题库-夸夸刷-必考题型专项拔高（上册）.pdf`: 225 pages, has usable standard question-book pages.
- `题本/2026资料分析题库-夸夸刷-必考题型专项拔高（下册）.pdf`: 216 pages, selected for demo because pages 9-12 are standard data-analysis question pages.

### Answer / Analysis Books

- `答本/解析篇.pdf`: 392 pages, answer/analysis book.
- `答本/最新：1200题解析.pdf`: 644 pages, answer/analysis book.
- `答本/test（7-12章下册完结）2026高照资料分析夸夸刷讲义复盘笔记（下册） .pdf`: 60 pages, review notes, not a question book.
- `答本/（7-12章下册完结）2026高照资料分析夸夸刷讲义复盘笔记（下册） .pdf`: 214 pages, review notes, not a question book.

## Selected Demo Sample

- Source PDF: `/Users/apple/Downloads/公考/project2/题本/2026资料分析题库-夸夸刷-必考题型专项拔高（下册）.pdf`
- Source page range: `9-12`
- Generated slice: `/tmp/admin-demo-question-book.pdf`
- Earlier equivalent slice: `/tmp/mvp-demo-question-bank.pdf`

## Demo Parse Results Already Verified

### Final Admin Demo Bank

- Bank name: `Admin题库Demo0429-204420`
- `bank_id`: `337945e8-ef97-4f99-a83d-1ed86cdb93d0`
- Uploaded file: `/tmp/admin-demo-question-book.pdf`
- `task_id`: `cec46786-9cdf-4f93-9fd0-569dd5d740c3`
- Parse status: `done`
- Parse count: `7`
- Publish result:
  - `published_count=7`
  - `bank_status=published`
  - `total_count=7`
- Admin question page:
  - `http://127.0.0.1:5173/banks/337945e8-ef97-4f99-a83d-1ed86cdb93d0/questions?taskId=cec46786-9cdf-4f93-9fd0-569dd5d740c3`
- Parse task page:
  - `http://127.0.0.1:5173/pdf/tasks`
- Export JSON command:
  - `curl "http://127.0.0.1:3010/admin/banks/337945e8-ef97-4f99-a83d-1ed86cdb93d0/export-json" -H "Authorization: Bearer <ADMIN_TOKEN>"`

### Current Demo Quality Problems

- All 7 questions are real questions and have A/B/C/D options.
- All 7 questions lack `answer` and `analysis`.
- `materials` returned empty.
- Some question stems include unwanted page header/footer or next material/title text.
- Image assignment is wrong or low-confidence in several cases.
- Existing parser succeeds technically, but output quality is not acceptable for production without review and repair.

## New Main Task

Fix data-analysis question-book PDF parsing and admin review editing capability.

## Reported Parsing Problems

- Header text like `资料分析题库-夸夸刷` enters `question.content`.
- Materials/charts are assigned to the wrong example question, such as example 2's table bound to example 1.
- Table stems and text stems are mixed.
- A table screenshot is split into two images, or multiple tables are wrongly merged.
- Cross-page question boundaries are confused.
- Admin review page cannot conveniently edit stems, options, images, and material assignment.
- Existing PDF locating/mobile preview buttons need to be extended or transformed into editing tools.

## Desired Architecture Direction

Move from pure chunk parsing to a semi-automatic production flow:

- Rule-based locating
- AI structural understanding
- Human review and correction

## Backend / Database Requirements

Check existing `Question`, `Material`, `QuestionImage`, and `ParseTask` entities first. Reuse similar existing fields before adding new ones.

Fields requested or equivalent fields needed:

- `source_page_start`
- `source_page_end`
- `source_bbox`
- `visual_refs`
- `parse_confidence`
- `parse_warnings`
- `image_role`: `material` / `question_visual` / `option_image` / `unknown`
- `image_order`
- `ai_desc`
- `review_status`

## Admin-Web Requirements

In question review page, add edit capability:

- Edit question stem `content`.
- Edit A/B/C/D options.
- Edit question type.
- View, delete, and sort question images.
- Move an image to previous/next question.
- Change image insertion position: above stem, below stem, above options, below options.
- Manually select PDF region and crop it into a question image.
- Merge adjacent images to fix split tables.
- Split current question, or merge current question into previous/next question.
- Add selected text to header/footer blacklist.
- Add `AI 修复当前题` button that reruns AI only for current question and related pages, not the full book.
- Refresh right-side H5 preview immediately after save.

## PDF-Service Requirements

### Header / Footer Detector

- Count repeated text across pages.
- Treat short text in top 0%-8% and bottom 0%-6% as default candidates.
- Repeated short text appearing more than 3 pages joins filter list.
- Filter:
  - `资料分析题库-夸夸刷`
  - page numbers
  - short chapter titles
  - table-of-contents residue
- Filtered text must not enter `question.content`.

### Question Boundary Detector

- Recognize `【例 1】`, `【例1】`, `1.`, `1、`, etc.
- Recognize A/B/C/D options.
- A question should contain at least stem and options, or explicitly be a material sub-question.
- From one question number to next question number is candidate block, excluding headers, footers, and chapter titles.
- Support cross-page continuation.

### Visual Assignment

- Preserve each visual area's `bbox`, `page_num`, `type`, `ocr_text`, and `caption`.
- Detect chart/table titles like `2012~2016 年社会消费品零售总额` and `表 1 ...`.
- Default visual assignment: bind visual to the nearest question number below it.
- If visual is above a question number and no other question number lies between, assign to that question.
- If one chart is referenced by multiple following questions, treat it as shared material.
- Never assign all visuals on a page to the first question unconditionally.

### Table Region Merge

- On the same page, merge multiple table/image bboxes when:
  - x-axis overlap is greater than 60%
  - y-gap is less than 8% of page height
  - no new question number lies between them
- Re-crop after merging.
- For cross-page tables, keep two images but mark `same_visual_group_id` so frontend can display continuously.

### Per-Page / Per-Question AI Repair

Input:

- page screenshot
- current candidate question bbox
- current OCR text
- current image bbox
- previous and next question summaries
- warning types

Strict JSON output:

```json
{
  "content": "",
  "options": {"A": "", "B": "", "C": "", "D": ""},
  "visual_refs": [],
  "material_text": "",
  "remove_texts": [],
  "warnings": [],
  "confidence": 0.0
}
```

AI only proposes corrections. It must not directly decide persisted data. Result must pass validator.

### Validator Enhancements

- Stem cannot contain header/footer blacklist text.
- Stem cannot contain large material text unless `question_type` is `material_sub`.
- Same image cannot bind to multiple non-shared questions.
- Abnormal image count should add warning.
- `content` containing `资料分析题库`, `夸夸刷`, or `第七章` should add warning.
- More than one `【例` in a stem should add `question_boundary_conflict`.
- Missing options should add `options_missing`.
- Low image assignment confidence should add `visual_assignment_low_confidence`.

## API Requirements

Add or reuse authenticated admin APIs:

- `GET /admin/questions/:id`
- `PATCH /admin/questions/:id`
- `POST /admin/questions/:id/images`
- `PATCH /admin/questions/:id/images/reorder`
- `POST /admin/questions/:id/move-image`
- `POST /admin/questions/:id/ai-repair`
- `POST /admin/pdf/crop-region`
- `POST /admin/pdf/header-footer-blacklist`
- `POST /admin/questions/:id/split`
- `POST /admin/questions/:id/merge`

## Acceptance Criteria

Use `/tmp/admin-demo-question-book.pdf` for validation.

- `资料分析题库-夸夸刷` must not enter stems.
- Example 1 only binds the wearable-device chart.
- Example 2 only binds the social retail sales chart.
- Example 3 binds the education-funding chart and does not include example 4's table.
- Example 4 binds the industrial big-data table.
- One table must not be split into two images without reason.
- Admin can manually edit stem, options, and images.
- H5 preview on the right refreshes after edits.
- Low-confidence questions keep warnings and should not be auto-published.
- Single-question AI repair must not affect other questions.

## Important Implementation Notes For Next Session

- Start by inspecting existing entities and migrations; do not add duplicate fields if equivalents already exist.
- Inspect `admin-web/src/views/banks/BankReviewView.vue` and related API modules before designing UI changes.
- Inspect `pdf-service` parser modules and current visual assignment logic before changing parser behavior.
- Prefer a staged implementation:
  - P0: backend fields/API + admin edit stem/options/images + header/footer filtering + boundary warnings.
  - P1: crop-region, image move/reorder/merge, split/merge question.
  - P2: single-question AI repair with validator.
- Do not auto-publish low-confidence repaired results.
- Keep changes minimal and test against `/tmp/admin-demo-question-book.pdf`.
