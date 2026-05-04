#!/usr/bin/env node
import { chromium, request } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const taskId = process.env.TASK_ID;
const outputDir = process.env.OUTPUT_DIR;
const adminBase = (process.env.ADMIN_BASE_URL || 'http://127.0.0.1:5173').replace(/\/+$/, '');
const backendBase = (process.env.BACKEND_BASE_URL || 'http://127.0.0.1:3010').replace(/\/+$/, '');
const chromeExecutablePath = process.env.CHROME_EXECUTABLE_PATH || '/usr/bin/google-chrome';
if (!taskId || !outputDir) throw new Error('TASK_ID and OUTPUT_DIR are required');

function unwrap(body, label) {
  if (body && typeof body === 'object' && typeof body.code === 'number') {
    if (body.code !== 0) throw new Error(`${label} API code=${body.code} message=${body.message || ''}`);
    return body.data;
  }
  return body;
}
async function login(ctx) {
  const candidates = [
    { phone: process.env.ADMIN_PHONE || 'admin', password: process.env.ADMIN_PASSWORD || 'admin' },
    { phone: process.env.ADMIN_PHONE || '13800138000', password: process.env.ADMIN_PASSWORD || '123456' },
  ];
  for (const cred of candidates) {
    const res = await ctx.post('/api/auth/login', { data: cred });
    if (!res.ok()) continue;
    const data = unwrap(await res.json(), '/api/auth/login');
    if (data?.access_token) return data.access_token;
  }
  throw new Error('admin login failed');
}
async function getJson(ctx, token, apiPath) {
  const res = await ctx.get(apiPath, { headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  if (!res.ok()) throw new Error(`${apiPath} HTTP ${res.status()}: ${text.slice(0, 500)}`);
  return unwrap(JSON.parse(text), apiPath);
}
function array(v) { return Array.isArray(v) ? v : []; }
function nums(questions) { return [...new Set(array(questions).map(q => Number(q?.question_no)).filter(Number.isFinite))].sort((a,b)=>a-b); }
function hasSpan(q) { return Boolean(String(q?.source_text_span || '').trim()); }
function hasBbox(q) { return Array.isArray(q?.source_bbox) && q.source_bbox.length === 4; }
function hasRefs(q) { return array(q?.source_page_refs).length > 0; }
function hasMaterial(q) { return Boolean(q?.material_group_id || q?.material_group || q?.material_group_key || q?.shared_material); }

await mkdir(outputDir, { recursive: true });
const audit = {
  taskId,
  checkedAt: new Date().toISOString(),
  adminBase,
  backendBase,
  api: {},
  ui: {},
  checks: {},
  coverage: {},
  screenshots: [],
  errors: [],
  warnings: [],
};
let browser, apiCtx;
try {
  apiCtx = await request.newContext({ baseURL: backendBase });
  const token = await login(apiCtx);
  const [task, paper, debug] = await Promise.all([
    getJson(apiCtx, token, `/admin/pdf/task/${taskId}`),
    getJson(apiCtx, token, `/admin/pdf/task/${taskId}/paper-candidates`),
    getJson(apiCtx, token, `/admin/pdf/task/${taskId}/ai-preaudit-debug`).catch(e => ({ error: e.message })),
  ]);
  await writeFile(path.join(outputDir, 'playwright-live-task-api.json'), JSON.stringify(task, null, 2) + '\n');
  await writeFile(path.join(outputDir, 'playwright-live-paper-candidates-api.json'), JSON.stringify(paper, null, 2) + '\n');
  await writeFile(path.join(outputDir, 'playwright-live-ai-preaudit-debug-api.json'), JSON.stringify(debug, null, 2) + '\n');
  const questions = array(paper.questions);
  const questionNos = nums(questions);
  audit.api = { status: task.status, totalCount: task.total_count, doneCount: task.done_count, questionNos, q7Present: questionNos.includes(7), questionCount: questions.length };
  audit.coverage = {
    sourceTextSpan: { present: questions.filter(hasSpan).length, total: questions.length },
    sourceBbox: { present: questions.filter(hasBbox).length, total: questions.length },
    sourcePageRefs: { present: questions.filter(hasRefs).length, total: questions.length },
    materialBinding: { present: questions.filter(hasMaterial).length, total: questions.length },
    canAddToPaperTrueCount: questions.filter(q => Boolean(q.can_add_to_paper || q.canAddToPaper)).length,
    manualForceAddAllowedTrueCount: questions.filter(q => Boolean(q.manualForceAddAllowed || q.manual_force_add_allowed)).length,
    needManualFixTrueCount: questions.filter(q => Boolean(q.need_manual_fix || q.needManualFix)).length,
  };

  browser = await chromium.launch({ headless: true, executablePath: chromeExecutablePath, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  await context.addInitScript((adminToken) => window.localStorage.setItem('admin_token', adminToken), token);
  const page = await context.newPage();
  page.on('console', msg => {
    if (!['error', 'warning'].includes(msg.type())) return;
    const entry = `console.${msg.type()}: ${msg.text()}`;
    if (/Failed to load resource:.*404/i.test(msg.text())) {
      audit.warnings.push(entry);
      return;
    }
    audit.errors.push(entry);
  });
  page.on('pageerror', err => audit.errors.push(`pageerror: ${err.message}`));
  await page.goto(`${adminBase}/pdf/tasks`, { waitUntil: 'networkidle', timeout: 30000 });
  audit.checks.adminWebReachable = true;
  await page.screenshot({ path: path.join(outputDir, 'admin-task-list.png'), fullPage: true });
  audit.screenshots.push(path.join(outputDir, 'admin-task-list.png'));
  await page.goto(`${adminBase}/pdf/tasks/${taskId}/paper-review`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.getByTestId('paper-review-overview').waitFor({ state: 'visible', timeout: 15000 });
  audit.checks.paperReviewReachable = true;
  await page.screenshot({ path: path.join(outputDir, 'admin-paper-review.png'), fullPage: true });
  audit.screenshots.push(path.join(outputDir, 'admin-paper-review.png'));
  const rowTexts = await page.locator('button.candidate-row').allInnerTexts();
  const bodyText = await page.locator('body').innerText();
  audit.ui = {
    candidateCount: rowTexts.length,
    rowTexts,
    q7PresentInRows: rowTexts.some(t => /第\s*7\s*题/.test(t)),
    q7PresentInBody: /第\s*7\s*题/.test(bodyText),
    bodyTextLength: bodyText.length,
  };
  audit.checks.q7PresentBackendApi = audit.api.q7Present;
  audit.checks.q7PresentAdminUi = audit.ui.q7PresentInRows || audit.ui.q7PresentInBody;
  audit.checks.failClosedNoManualForce = audit.coverage.manualForceAddAllowedTrueCount === 0;
  audit.checks.failClosedNoCanAdd = audit.coverage.canAddToPaperTrueCount === 0;
  await context.tracing.stop({ path: path.join(outputDir, 'playwright-trace.zip') });
  await browser.close(); browser = null;
  await apiCtx.dispose(); apiCtx = null;
} catch (e) {
  audit.errors.push(e.stack || e.message);
  try { if (browser) await browser.close(); } catch {}
  try { if (apiCtx) await apiCtx.dispose(); } catch {}
}

const lines = [
  '# Phase A M2 Playwright/API/Admin UI Audit',
  `- task_id: ${taskId}`,
  `- checked_at: ${audit.checkedAt}`,
  `- api_question_numbers: ${(audit.api.questionNos || []).join(',')}`,
  `- api_q7_present: ${Boolean(audit.api.q7Present)}`,
  `- admin_ui_q7_present: ${Boolean(audit.checks.q7PresentAdminUi)}`,
  `- ui_candidate_count: ${audit.ui.candidateCount ?? 'n/a'}`,
  `- source_text_span: ${audit.coverage.sourceTextSpan?.present ?? 0}/${audit.coverage.sourceTextSpan?.total ?? 0}`,
  `- source_bbox: ${audit.coverage.sourceBbox?.present ?? 0}/${audit.coverage.sourceBbox?.total ?? 0}`,
  `- source_page_refs: ${audit.coverage.sourcePageRefs?.present ?? 0}/${audit.coverage.sourcePageRefs?.total ?? 0}`,
  `- material_binding: ${audit.coverage.materialBinding?.present ?? 0}/${audit.coverage.materialBinding?.total ?? 0}`,
  `- canAddToPaper_true_count: ${audit.coverage.canAddToPaperTrueCount ?? 'n/a'}`,
  `- manualForceAddAllowed_true_count: ${audit.coverage.manualForceAddAllowedTrueCount ?? 'n/a'}`,
  '',
  '## Screenshots/trace',
  ...audit.screenshots.map(p => `- ${p}`),
  `- ${path.join(outputDir, 'playwright-trace.zip')}`,
  '',
  '## Errors',
  ...(audit.errors.length ? audit.errors.map(e => `- ${e}`) : ['- none']),
  '',
  '## Warnings',
  ...(audit.warnings.length ? audit.warnings.map(e => `- ${e}`) : ['- none']),
  '',
];
await writeFile(path.join(outputDir, 'playwright-recognition-audit.json'), JSON.stringify(audit, null, 2) + '\n');
await writeFile(path.join(outputDir, 'PLAYWRIGHT_RECOGNITION_AUDIT_REPORT.md'), lines.join('\n'));
console.log(JSON.stringify({ outputDir, q7Api: audit.api.q7Present, q7Ui: audit.checks.q7PresentAdminUi, errors: audit.errors }, null, 2));
if (audit.errors.length) process.exitCode = 2;
