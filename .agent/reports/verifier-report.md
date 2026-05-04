# Verifier Report

- task_id: 836fec20-2628-44ed-9642-aedd57467864
- m2_verdict: M2_PASS
- m3_verdict: M3_PASS
- m4_verdict: M4_FAIL
- produced_question_count: 20/20
- missing_question_numbers: []
- fallback_failed_pages: []
- debug_live_consistency: pass

## M2 Checks

- task_status=done
- progress=100
- produced_question_count=20/20
- fallback_failed_pages=[]
- missing_question_numbers=[]
- page_5_questions_16_20_recovered
- debug_live_consistency=pass
- manualForceAddAllowed_true_count=0
- warning_or_failed_can_add_count=0
- provider_health:qwen+ark=pass
- backend_test:pdf-review-workflow=pass
- pdf-service:test_scanned_question_book_kernel=pass
- pdf-service:test_ai_client_page_visual_fallbacks=pass
- pdf-service:test_provider_health_report=pass

## Failed Checks

- none

## M4 Metrics

- ai_audit_status_present: 20/20
- answer_suggestion_present: 0/20
- answer_unknown_reason_present: 20/20
- analysis_suggestion_present: 0/20
- analysis_unknown_reason_present: 20/20
- visual_summary_present: 0/20
- image_linkage_complete: 0/20

## Evidence Paths

- /home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/final-questions.json
- /home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/fallback-recovery.json
- /home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/question-number-scan.json
- /home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/paper-candidate-payload.json
- /home/carry/project2/.agent/reports/provider-health-report.json
- /home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/playwright-recognition-audit.json
- /home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/playwright-live-paper-candidates-api.json
- /home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/admin-paper-review.png
- /home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/playwright-trace.zip
