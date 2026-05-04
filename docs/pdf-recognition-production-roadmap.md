# PDF Recognition Production Roadmap

## 1. Whole-page Understanding

- Parse each page as a whole before cutting small crops.
- Detect question numbers, stems, options, shared materials, charts, chart titles, legends, table headers, axis labels, footnotes, and cross-page links.
- Persist page-level evidence even when model output is malformed: rendered image path, OCR/vision status, raw output ref, schema errors, and uncertain regions.

## 2. Semantic Grouping

- Build explicit groups per question:
  - `stem_group`
  - `options_group`
  - `material_group`
  - `visual_group`
  - `title_group`
  - `notes_group`
- Shared materials must be represented as first-class material groups and linked to all dependent questions.
- Cross-page groups must carry source page ranges and missing-page risk flags.

## 3. Recrop Plan

- Generate recrop plans from semantic groups, not from isolated image boxes.
- Required crop context:
  - stem
  - all options
  - full chart/table
  - chart title
  - legend
  - axis labels
  - table headers
  - footnotes
- If a crop cannot include required context, mark `need_manual_fix` and keep the rejected crop evidence.

## 4. Source Locator

- `paper-review` must be able to open the original page and highlight source regions.
- Candidates must expose:
  - `source_page_refs`
  - `source_bbox`
  - `source_text_span`
- No source locator means `manualReviewable=false`.
- Partial context and missing previous page must remain hard blockers for auto add and manual force add.

## 5. AI Pre-audit

Each candidate should include:

- `ai_audit_status`
- `ai_audit_verdict`
- `ai_audit_summary`
- `answer_suggestion`
- `analysis_suggestion`
- `risk_flags`
- `can_answer`
- `suggested_action`

Pre-audit must not invent answers or analyses. Unknown answers require `answer_unknown_reason`; unknown analyses require `analysis_unknown_reason`.

## 6. Similarity / Duplicate

Recommended staged approach:

- Exact hash for identical source crops and normalized text.
- Normalized text comparison for near-duplicates.
- FTS / pgvector nearest-neighbor recall for semantic similarity.
- pHash / `visual_group_hash` for chart/table/image similarity.
- Classify edges as `duplicate`, `near`, `sibling`, or `similar`.
- Add a reviewer similarity panel before canonical ingest.
- Never write unauthorized external parse results directly into canonical question tables.

## 7. Task Governance

Short term:

- BullMQ / Redis parent-child chunk execution.
- `parse_tasks` and `parse_chunks` status separation.
- Chunk retry and partial save.
- Progress API by stage.
- Failed-stage observability with `stage-counts.json` and `first-failed-stage.json`.

Medium term:

- Consider Temporal only after parse chunks, retries, artifacts, and reviewer workflows stabilize.

## 8. Data Tables

Suggested future tables:

- `source_documents`
- `parse_tasks`
- `parse_chunks`
- `page_artifacts`
- `materials`
- `questions`
- `question_versions`
- `question_similarity_edges`
- `audit_events`

Do not introduce the full schema until parser artifacts and review workflows are stable.

## 9. Compliance

- Store rights metadata for uploaded documents.
- Keep model-call logs and artifact references.
- Require uploader warranty for rights/usage.
- Maintain takedown and audit trail workflows.
