# Hermes PDF Production Pipeline Checkpoint

Timestamp: 2026-05-01 17:23:18 CST
Branch: hermes/pdf-production-pipeline

## Scope

This is a local/remote WIP checkpoint for the Hermes handoff and M1 Vision Provider Reliability & Fallback work. It is intentionally not a final product report and does not advance M2-M8.

Committed scope is limited to PDF recognition pipeline governance/diagnostics code and lightweight documentation:

- pdf-service routing / parser-kernel diagnostic hardening.
- backend paper-review diagnostic artifact exposure.
- fixture and paper-review recognition regression scripts.
- lightweight acceptance / roadmap documentation.

Large debug artifacts, screenshots, PDFs, JSON payloads, node_modules, .venv, dist, coverage, local env files, and provider credentials are not included.

## Current M1 Status

Main positive fixture:

- PDF: /Users/apple/Downloads/题本篇-1-8.pdf
- Fixture sanity: pass.
- Confirmed image-only scanned question book.
- Rendered pages: 8 / 8.
- Actual kind: scanned_question_book.
- Previous default/reused audit still failed as zero_questions_extracted because the recognition script reused an old done task.
- New forced parse task: 1a43676e-14d6-4a71-8b81-d4442f08fb43.
- New forced parse produced paper candidates, so it is no longer a pure zero-questions path:
  - total candidates: 4
  - question numbers observed: 8, 9, 10, 1
  - can_add_count: 0
  - ai_warning_count: 4
  - ai_passed_count: 0
  - manualForceAddAllowed remains false for source/material/evidence gaps.
- Current remaining issue: source/material locator evidence is still incomplete; stage_counts / first_failed_stage are not yet propagated into this existing backend debug payload unless backend is restarted with the checkpointed code.
- Expected fail classification for this checkpoint:
  - main positive recognition: fail expected / partial M1 pass
  - firstFailedStage: source_evidence_missing or backend diagnostics propagation missing for the new forced task; old reused task shows render_or_vision / zero_questions_extracted
  - failureReason: main positive now yields candidates but lacks reviewable source/material evidence for automatic/manual add
  - recommendedFix: restart backend with this checkpoint, rerun FORCE_NEW_PARSE=1 main_positive_fixture, then continue M1 hardening before M2/M8

Negative regression:

- PDF: /Users/apple/Downloads/公考/project2/backend/sample-题本篇-3-7.pdf
- Role: partial_pdf_context_negative_regression
- Result: pass in latest run.
- Safety invariants retained:
  - cannot auto ingest
  - cannot auto compose
  - cannot publish
  - manual force add remains unavailable for incomplete source/material/evidence

## Key Changes

### pdf-service

- Added routing_decision / filename_hint / page reality evidence so filename is treated as a hint rather than the only route signal.
- Added parser-kernel vision failure classification and richer page-level diagnostics for timeout, empty response, schema invalid, schema repair/fallback failures, and visual model failures.
- Added failed page details propagation to parser-kernel debug payloads.
- Added page-understanding fallback metadata so visual failures can still leave coarse evidence.
- Default debug smoke page range now uses PDF_DEBUG_SMOKE_PAGES with 1-8 default instead of hard-coded 9-14.

### backend

- Exposes final_questions, stage_counts, first_failed_stage, and diagnostics in paper-review debug/paper-candidate payloads.
- Writes stage-counts.json and first-failed-stage.json when backend consumes parser-kernel artifacts.
- Adds backend invariants for kernel output present but final preview / paper candidates empty.

### scripts

- check-pdf-fixtures.mjs now performs fixture sanity and page-reality analysis for main positive, negative regression, full scanned source, and candidate page ranges.
- check-paper-review-recognition.mjs now supports FIXTURE_ROLE=all and FORCE_NEW_PARSE=1 to avoid silently reusing stale done tasks during diagnostics.
- Recognition audit now writes zero-candidate reports with first failed stage and stage counts where available.

### docs

- Updated PDF image recognition acceptance notes with fixture role matrix, first-failed-stage expectations, and safety invariants.
- Added production roadmap stub covering whole-page understanding, semantic grouping, recrop plan, source locator, AI pre-audit, similarity, task governance, and future schema.

## Commands Run Before Commit

Required checks:

- git branch --show-current: hermes/pdf-production-pipeline
- git status --short: modified PDF pipeline files plus untracked docs/report files; no sensitive large artifacts selected for commit
- git remote -v: origin https://github.com/carrywu/Unione.git
- cd pdf-service && .venv/bin/python -m unittest: exit 5, expected command behavior because default unittest discovery ran 0 tests
- cd pdf-service && .venv/bin/python -m unittest discover -s tests -p 'test*.py': pass, 84 tests OK
- python3 -m py_compile pdf-service/pipeline.py pdf-service/parser_kernel/routing.py pdf-service/parser_kernel/adapter.py pdf-service/models.py pdf-service/vision_ai/qwen_vl_provider.py pdf-service/vision_ai/enhancer.py pdf-service/vision_ai/schema.py pdf-service/vision_ai/prompt_builder.py pdf-service/ai_client.py: pass
- cd backend && npm run build: pass
- node --check scripts/check-pdf-fixtures.mjs: pass
- node --check scripts/check-paper-review-recognition.mjs: pass
- node scripts/check-pdf-fixtures.mjs: pass
- FIXTURE_ROLE=partial_pdf_context_negative_regression node scripts/check-paper-review-recognition.mjs: pass

Additional evidence:

- Latest fixture sanity output: /Users/apple/Downloads/公考/project2/debug/paper-review/20260501-172205/pdf-fixtures-check.json
- Latest negative regression audit: /Users/apple/Downloads/公考/project2/debug/paper-review/20260501-172251/recognition-audit.json
- New forced main-positive candidate payload: /Users/apple/Downloads/公考/project2/backend/debug/pdf-ai-preaudit/1a43676e-14d6-4a71-8b81-d4442f08fb43/paper-candidate-payload.json

## Not Included In Commit

- deep-research-report.md: left untracked; research-sized document, not part of this stage checkpoint.
- debug/hermes/* and debug/paper-review/* large artifacts: intentionally not committed.
- PDFs, rendered PNGs, raw model outputs, local environment files, credentials, node_modules, .venv, dist, coverage: not committed.

## Follow-up Needed

1. Restart backend with this checkpointed code so stage_counts / first_failed_stage are written for new tasks.
2. Rerun FORCE_NEW_PARSE=1 FIXTURE_ROLE=main_positive_fixture node scripts/check-paper-review-recognition.mjs after backend restart.
3. Continue M1 Vision Provider Reliability & Fallback hardening before starting M2/M8.
4. Do not loosen partial_pdf_context or missing_previous_page_context safety rules.
