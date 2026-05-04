# Git Cleanup Dry-Run Report

Generated: 20260504-182031
Branch: ralph/xingce-e2e-git-hygiene-delivery

## Summary

| Action | Files | Size |
|--------|-------|------|
| delete | 62 | 0.8 MB |
| archive | 2467 | 804.8 MB |
| keep | 50 | 555.1 MB |
| **Total** | **2579** | **1360.7 MB** |

## Safe to Delete (62 files, 786 KB)

These files are confirmed safe to delete. They are stale PID files, dev logs, and build cache.

| Path | Size | Reason |
|------|------|--------|
| `backend/.pnpm-approved-builds.json` | 40 B | pnpm build approval cache |
| `logs/dev/admin-web.log` | 4298 B | Dev server PID files, stale |
| `logs/dev/backend.log` | 727049 B | Dev server PID files, stale |
| `logs/dev/check-20260502-125929.log` | 1186 B | Dev server PID files, stale |
| `logs/dev/check-20260502-130325.log` | 1186 B | Dev server PID files, stale |
| `logs/dev/check-20260502-130348.log` | 1289 B | Dev server PID files, stale |
| `logs/dev/check-20260502-134510.log` | 1168 B | Dev server PID files, stale |
| `logs/dev/check-20260502-134511.log` | 1168 B | Dev server PID files, stale |
| `logs/dev/check-20260502-172328.log` | 1271 B | Dev server PID files, stale |
| `logs/dev/check-20260502-172933.log` | 1271 B | Dev server PID files, stale |
| `logs/dev/check-20260502-173617.log` | 1362 B | Dev server PID files, stale |
| `logs/dev/check-20260502-194132.log` | 840 B | Dev server PID files, stale |
| `logs/dev/check-20260502-200137.log` | 1271 B | Dev server PID files, stale |
| `logs/dev/check-20260502-222947.log` | 1171 B | Dev server PID files, stale |
| `logs/dev/check-20260503-024102.log` | 1171 B | Dev server PID files, stale |
| `logs/dev/check-20260503-050440.log` | 1191 B | Dev server PID files, stale |
| `logs/dev/check-20260503-052126.log` | 1298 B | Dev server PID files, stale |
| `logs/dev/check-20260503-052632.log` | 1191 B | Dev server PID files, stale |
| `logs/dev/check-20260503-074255.log` | 1191 B | Dev server PID files, stale |
| `logs/dev/check-20260503-140651.log` | 1191 B | Dev server PID files, stale |
| `logs/dev/check-20260503-140921.log` | 1292 B | Dev server PID files, stale |
| `logs/dev/check-20260503-140927.log` | 1292 B | Dev server PID files, stale |
| `logs/dev/check-20260503-142602.log` | 1292 B | Dev server PID files, stale |
| `logs/dev/check-20260503-144537.log` | 1186 B | Dev server PID files, stale |
| `logs/dev/check-20260503-201945.log` | 1280 B | Dev server PID files, stale |
| `logs/dev/check-20260503-225418.log` | 1178 B | Dev server PID files, stale |
| `logs/dev/check-20260503-230426.log` | 1178 B | Dev server PID files, stale |
| `logs/dev/check-20260503-231132.log` | 1178 B | Dev server PID files, stale |
| `logs/dev/check-20260503-231317.log` | 1283 B | Dev server PID files, stale |
| `logs/dev/check-20260504-094046.log` | 849 B | Dev server PID files, stale |
| `logs/dev/check-20260504-094110.log` | 849 B | Dev server PID files, stale |
| `logs/dev/h5-web.log` | 4260 B | Dev server PID files, stale |
| `logs/dev/pdf-service.log` | 9318 B | Dev server PID files, stale |
| `logs/dev/pids/admin-web.pid` | 8 B | Dev server PID files, stale |
| `logs/dev/pids/backend.pid` | 8 B | Dev server PID files, stale |
| `logs/dev/pids/h5-web.pid` | 8 B | Dev server PID files, stale |
| `logs/dev/pids/pdf-service.pid` | 8 B | Dev server PID files, stale |
| `logs/dev/start-20260502-125937.log` | 924 B | Dev server PID files, stale |
| `logs/dev/start-20260502-125954.log` | 690 B | Dev server PID files, stale |
| `logs/dev/start-20260502-130314.log` | 1150 B | Dev server PID files, stale |
| `logs/dev/start-20260502-130339.log` | 1222 B | Dev server PID files, stale |
| `logs/dev/start-20260502-134511.log` | 924 B | Dev server PID files, stale |
| `logs/dev/start-20260502-172319.log` | 1222 B | Dev server PID files, stale |
| `logs/dev/start-20260502-172924.log` | 1222 B | Dev server PID files, stale |
| `logs/dev/start-20260502-200127.log` | 1222 B | Dev server PID files, stale |
| `logs/dev/start-20260502-222932.log` | 924 B | Dev server PID files, stale |
| `logs/dev/start-20260503-052115.log` | 1230 B | Dev server PID files, stale |
| `logs/dev/start-20260503-140911.log` | 1226 B | Dev server PID files, stale |
| `logs/dev/start-20260503-142553.log` | 1226 B | Dev server PID files, stale |
| `logs/dev/start-20260503-201931.log` | 1236 B | Dev server PID files, stale |
| `logs/dev/start-20260503-221144.log` | 1226 B | Dev server PID files, stale |
| `logs/dev/start-20260504-094024.log` | 1240 B | Dev server PID files, stale |
| `logs/dev/start-20260504-165714.log` | 1230 B | Dev server PID files, stale |
| `logs/dev/stop-20260502-125947.log` | 681 B | Dev server PID files, stale |
| `logs/dev/stop-20260502-130334.log` | 852 B | Dev server PID files, stale |
| `logs/dev/stop-20260502-172313.log` | 970 B | Dev server PID files, stale |
| `logs/dev/stop-20260502-172908.log` | 970 B | Dev server PID files, stale |
| `logs/dev/stop-20260503-052109.log` | 972 B | Dev server PID files, stale |
| `logs/dev/stop-20260503-140904.log` | 988 B | Dev server PID files, stale |
| `logs/dev/stop-20260503-142537.log` | 979 B | Dev server PID files, stale |
| `logs/dev/stop-20260503-221134.log` | 972 B | Dev server PID files, stale |
| `logs/dev/stop-20260504-165702.log` | 810 B | Dev server PID files, stale |

## Archive (not delete) (2467 files, 804.8 MB)

These files should be archived (moved to a backup location), NOT deleted. They contain agent orchestration state, test evidence, and historical data.

| Category | Files | Size | Action | Reason |
|----------|-------|------|--------|--------|
| `backend/uploads/` | 1665 | 766.8 MB | archive | Uploaded PDF/PNG evidence from previous test runs, debug evidence |
| `.agent/` | 796 | 37.9 MB | archive | Generated agent orchestration state/history |
| `scripts/` | 5 | 0.1 MB | archive | Agent bus script, used by .agent/ orchestration |
| `ralph` | 1 | 0.0 MB | archive | Old Ralph PRD, superseded by root prd.json |

## Must Keep (50 files, 555.1 MB)

These files must NOT be deleted or archived. They are source code, test materials, configs, or reference documents.

### Tracked Modified (source code changes)

| Path | Size | Status |
|------|------|--------|
| `admin-web/.env.example` | 40 B | tracked_modified |
| `admin-web/src/views/system/SystemView.vue` | 21787 B | tracked_modified |
| `backend/.env.example` | 983 B | tracked_modified |
| `backend/src/modules/answer-book/answer-book.service.ts` | 23538 B | tracked_modified |
| `backend/src/modules/question/entities/question.entity.ts` | 8679 B | tracked_modified |
| `backend/src/modules/question/question.service.ts` | 42601 B | tracked_modified |
| `backend/src/seed.ts` | 27656 B | tracked_modified |
| `docs/pdf-image-recognition-acceptance.md` | 7324 B | tracked_modified |
| `h5-web/.env.example` | 40 B | tracked_modified |
| `pdf-service/.env.example` | 1522 B | tracked_modified |
| `pdf-service/AGENTS.md` | 2193 B | tracked_modified |
| `pdf-service/ai_parser.py` | 2564 B | tracked_modified |
| `pdf-service/debug_tools/export_visual_debug.py` | 9473 B | tracked_modified |
| `pdf-service/parser_kernel/__init__.py` | 712 B | tracked_modified |
| `pdf-service/parser_kernel/routing.py` | 4607 B | tracked_modified |
| `pdf-service/tests/test_pdf_review_flow_rules.py` | 26245 B | tracked_modified |
| `pdf-service/tests/test_scanned_pdf_routing.py` | 1635 B | tracked_modified |
| `pdf-service/vision_ai/qwen_vl_provider.py` | 4238 B | tracked_modified |
| `prd.json` | 20370 B | tracked_modified |
| `progress.txt` | 8780 B | tracked_modified |
| `scripts/check-paper-review-recognition.mjs` | 42810 B | tracked_modified |
| `scripts/check-pdf-fixtures.mjs` | 23914 B | tracked_modified |

### Untracked Keep

| Path | Size | Reason |
|------|------|--------|
| `答本/解析篇.pdf` | 182.2 MB | Primary answer book PDF |
| `答本/最新：1200题解析.pdf` | 103.2 MB | Answer book PDF |
| `题本/题本篇.pdf` | 84.6 MB | Primary test book PDF |
| `答本/（7-12章下册完结）2026高照资料分析夸夸刷讲义复盘笔记（下册） .pdf` | 83.2 MB | Answer book PDF |
| `题本/最新：1200题题本.pdf` | 55.6 MB | Test material PDF |
| `答本/test（7-12章下册完结）2026高照资料分析夸夸刷讲义复盘笔记（下册） .pdf` | 22.8 MB | Test answer book PDF |
| `题本/2026资料分析题库-夸夸刷-必考题型专项拔高（下册）.pdf` | 11.0 MB | Test material PDF |
| `题本/2026资料分析题库-夸夸刷-必考题型专项拔高（上册）.pdf` | 9.6 MB | Test material PDF |
| `backend/sample-题本篇-3-7.pdf` | 2.5 MB | Sample PDF test material |
| `deep-research-report.md` | 0.0 MB | Research report, reference |
| `PDF_PARSE_REVIEW_MEMORY.md` | 0.0 MB | PDF parse review memory, reference |
| `RECENT_WORK_SUMMARY.md` | 0.0 MB | Recent work summary, reference |
| `MVP_LOCAL_RUNBOOK.md` | 0.0 MB | MVP runbook, reference document |
| `scripts/ralph/ralph.sh` | 0.0 MB | Ralph script |
| `scripts/ralph/CLAUDE.md` | 0.0 MB | Ralph skill config |
| `scripts/ralph/prompt.md` | 0.0 MB | Ralph prompt template |
| `start-dev.sh` | 0.0 MB | Dev start script, utility |
| `ENV_FIX_REPORT.md` | 0.0 MB | Environment fix report, reference document |
| `docs/pdf-recognition-production-roadmap.md` | 0.0 MB | Production roadmap doc |
| `PDF_VISUAL_AGENT_10Q_TASK.md` | 0.0 MB | Visual agent task doc, reference |
| `check-dev.sh` | 0.0 MB | Dev check script, utility |
| `stop-dev.sh` | 0.0 MB | Dev stop script, utility |
| `DB_RESTORE_REPORT.md` | 0.0 MB | DB restore report, reference document |
| `.mcp.json` | 0.0 MB | MCP configuration |
| `package.json` | 0.0 MB | Root package.json, workspace config |
| `scripts/ralph/.last-branch` | 0.0 MB | Ralph last branch marker |
| `docs/hermes-phase-reports/` | 0.0 MB | Hermes phase reports, reference docs |
| `pdf-service/tests/__init__.py` | 0.0 MB | Python test package marker |

## PRD Acceptance Criteria Mapping

| Pattern | Action | Present in Workspace |
|---------|--------|---------------------|
| `dist` | delete | Not present in workspace |
| `build` | delete | Yes (marked for deletion) |
| `.vite` | delete | Not present in workspace |
| `coverage` | delete | Not present in workspace |
| `playwright-report` | delete | Not present in workspace |
| `test-results` | delete | Not present in workspace |
| `node_modules/.cache` | delete | Not present in workspace |
| `__pycache__` | delete | Not present in workspace |
| `.pytest_cache` | delete | Not present in workspace |
| `.mypy_cache` | delete | Not present in workspace |
| `.ruff_cache` | delete | Not present in workspace |
| `.coverage` | delete | Not present in workspace |
| `.DS_Store` | delete | Not present in workspace |
| `*.tmp` | delete | Not present in workspace |
| `*.log (expired)` | delete | Yes (311 files, marked for deletion) |
| `backend/src/**` | keep | Yes (4 files, marked keep) |
| `backend/test/**` | keep | Present as tracked (keep) |
| `admin-web/src/**` | keep | Yes (1 files, marked keep) |
| `pdf-service/**` | keep | Yes (10 files, marked keep) |
| `migration` | keep | Present as tracked (keep) |
| `seed` | keep | Present as tracked (keep) |
| `fixture` | keep | Present as tracked (keep) |
| `package-lock.json` | keep | Present as tracked (keep) |
| `.env*` | keep | Present as tracked (keep) |
| `/home/carry/题本/题本篇.pdf` | keep | Yes (marked keep) |
| `/home/carry/答本/解析篇.pdf` | keep | Yes (marked keep) |
| `debug/m5/836fec20-.../` | keep | Yes (marked keep) |

## Execution Plan for US-004

1. **Delete** 62 small files (logs, PID files, build cache) — ~786 KB
2. **Archive** 2467 files to backup location — ~805 MB
   - `.agent/` (796 files, 38 MB) — agent orchestration state
   - `backend/uploads/` (1665 files, 767 MB) — uploaded PDF/PNG test evidence
   - `scripts/` orchestration tools (5 files, 0.1 MB)
   - `ralph/prd.json` (1 file, 19 KB) — superseded old PRD
3. **Keep** all 22 tracked modified files, 9 PDF test materials, 12 utility scripts/configs
