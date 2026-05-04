# Ralph Baseline - 行测助手项目

Generated: 2026-05-04 18:39:32 CST
Branch: ralph/xingce-e2e-git-hygiene-delivery

## Project Structure

```
/home/carry/project2/
├── backend/          # NestJS backend (TypeScript)
├── admin-web/        # Vue 3 + Element Plus admin frontend
├── h5-web/           # Vue 3 + Vant 4 mobile frontend
├── pdf-service/      # FastAPI PDF parsing service (Python)
├── scripts/          # Utility scripts
├── docs/             # Documentation
├── 题本/             # Test book PDFs (9 files, ~160 MB)
├── 答本/             # Answer book PDFs (4 files, ~391 MB)
├── debug/            # Debug evidence (gitignored)
└── prd.json          # Ralph PRD (canonical)
```

## Services & Ports

| Service | Tech Stack | Port | Entry Point |
|---------|-----------|------|-------------|
| Backend | NestJS (TypeScript) | 3000 | `backend/src/main.ts` |
| Admin Web | Vue 3 + Element Plus | 5173 | `admin-web/vite.config.ts` |
| H5 Web | Vue 3 + Vant 4 | 5173 | `h5-web/vite.config.ts` |
| PDF Service | FastAPI (Python) | 8001 | `pdf-service/main.py` |
| MySQL | MySQL | 3306 | localhost |
| Redis | Redis | 6379 | localhost |

## Environment Variables

### Backend (.env.example)
- `PORT=3000`
- `DB_HOST=localhost`, `DB_PORT=3306`, `DB_USER=root`, `DB_NAME=quiz_app`
- `REDIS_HOST=localhost`, `REDIS_PORT=6379`
- `PDF_SERVICE_URL=http://localhost:8001`
- `BACKEND_URL=http://127.0.0.1:3010`
- `JWT_SECRET`, `JWT_ACCESS_EXPIRE=2h`, `JWT_REFRESH_EXPIRE=7d`
- `UPLOAD_PROVIDER=local`
- AI keys: `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`, `ARK_BASE_URL`

### PDF Service (.env.example)
- `VISION_AI_PROVIDER_ORDER=volcengine_ark_vl,qwen_vl,mimo_vl`
- `VISION_AI_TIMEOUT_SECONDS=60`
- `VISION_AI_MAX_RETRIES=2`
- `ENABLE_VISION_AI=false` (disabled by default)
- `ENABLE_AI_SOLVER=false` (disabled by default)

## Package Scripts

### Backend
- `npm run start:dev` — NestJS dev server with watch
- `npm run build` — NestJS production build
- `npm run seed` — Run database seeder
- `npm run test:smoke` — Smoke test via `scripts/backend-smoke.mjs`

### Admin Web
- `npm run dev` — Vite dev server
- `npm run build` — Production build (vue-tsc + vite)

### PDF Service
- `uvicorn main:app --port 8001` — FastAPI dev server
- `python -m pytest` — Python tests

## Default Quality Checks
```bash
cd /home/carry/project2/backend && node -r ts-node/register -r tsconfig-paths/register test/pdf-review-workflow.test.ts
cd /home/carry/project2/backend && npm run build
cd /home/carry/project2/admin-web && npm run build
```

## Git Status After Cleanup

- 20 tracked modified files (source code changes pending)
- 19 untracked files (utility scripts, test materials, docs)
- Git status reduced from 400+ → 39 lines after US-001 through US-005

### Tracked Modified Files (uncommitted source changes)
- `admin-web/src/views/system/SystemView.vue`
- `backend/src/modules/answer-book/answer-book.service.ts`
- `backend/src/modules/question/entities/question.entity.ts`
- `backend/src/modules/question/question.service.ts`
- `backend/src/seed.ts`
- `pdf-service/ai_parser.py`
- `pdf-service/debug_tools/export_visual_debug.py`
- `pdf-service/parser_kernel/__init__.py`
- `pdf-service/parser_kernel/routing.py`
- `pdf-service/tests/test_pdf_review_flow_rules.py`
- `pdf-service/tests/test_scanned_pdf_routing.py`
- `pdf-service/vision_ai/qwen_vl_provider.py`
- `scripts/check-paper-review-recognition.mjs`
- `scripts/check-pdf-fixtures.mjs`
- `.env.example` files (4: admin-web, backend, h5-web, pdf-service)
- `docs/pdf-image-recognition-acceptance.md`

### Known Test Materials
- 题本 PDF: `/home/carry/题本/题本篇.pdf`
- 答本 PDF: `/home/carry/答本/解析篇.pdf`
- Real task ID: `836fec20-2628-44ed-9642-aedd57467864`
- M5A report: `debug/m5/836fec20-2628-44ed-9642-aedd57467864/`
