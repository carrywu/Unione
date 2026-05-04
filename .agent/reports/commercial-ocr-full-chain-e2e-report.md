# Commercial OCR Full-Chain E2E Report

## Summary

- Branch: `main`
- Code baseline before report commit: `864ff7d`
- Push target: `origin/main`
- Default OCR mode for this run: `mock_commercial_ocr`
- Real Tencent/Baidu API: skipped

## Integration Status

- backend: commercial OCR provider metadata, material groups, visual understanding, quality gate, and fallback flags are wired into review and preview DTOs
- pdf-service: provider orchestration, OCR normalization, semantic assembly, visual understanding mock, and quality gate all run in one response path
- admin-web: reviewer can see provider, quality gate, shared material, grouping evidence, warnings, similarity state, and publish gate
- h5-web: preview paper preserves shared material across 17-20 and shows answer/analysis without duplicating material text

## E2E Status

- Admin Playwright: `2 passed`
  - blocked fixture stays gated out of draft/publish
  - complete fixture can be reviewed and preview-published
- H5 Playwright: `1 passed`
  - preview paper preserves shared material across 17-20 on mobile viewport

## Artifact Paths

- admin blocked: `debug/e2e-commercial-ocr/20260505-014457/admin/blocked-review-gate/`
- admin publishable: `debug/e2e-commercial-ocr/20260505-014457/admin/complete-preview-publish/`
- h5 mobile: `debug/e2e-commercial-ocr/20260505-014457/h5/preview-paper-mobile/`

## 17-20 Shared Material Acceptance

- blocked fixture: 17-20 remained a single material group, but `quality_gate.review_ready=false`, draft creation correctly rejected
- publishable fixture: 17/18/19/20 shared one material group, shared assets stayed attached, `local_stem` did not repeat `shared_stem`, preview publish succeeded, h5 preview kept the shared material visible across all four questions

## Publish Gate Acceptance

- rejected:
  - incomplete OCR fixture with missing options / missing answer / `analysis=unknown`
  - blocked draft creation returned `400`
- allowed:
  - complete shared-material fixture with `review_ready=true`
  - preview publish route returned `/quiz-preview/<paperId>`

## M5A / M5B Regression Status

- M5A: no regression observed in backend DTO wiring; answer-book alignment paths were preserved and not bypassed
- M5B: no regression observed in review UI; similarity panel rendered stable empty/candidate state instead of `undefined` / `[object Object]`

## Regression Cleanup

- fixed `test_ark_provider_smoke_classifies_auth_error`
- fixed `test_ark_provider_smoke_falls_back_from_endpoint_id_to_default_model`
- fixed `test_retry_failed_pages_only_bypasses_failed_cache_and_merges_manifest`
- full `pdf-service` pytest is now `144 passed / 2 skipped`

## Remaining Risks

- real provider smoke remains gated
- visual understanding is mock-only
- backend has no standalone `/api/health`
- Baidu keys were exposed in chat earlier and must be rotated

## Next Recommendations

1. M5 hardening: replace mock visual understanding with selected-case real VLM validation.
2. M8 real adapter hardening: add single-page Tencent/Baidu smoke jobs with explicit flags, 429/backoff, and provider conflict evidence.
3. M9/M12 follow-up: decide whether warning cases can be manually force-published and encode that policy in UI/API.
