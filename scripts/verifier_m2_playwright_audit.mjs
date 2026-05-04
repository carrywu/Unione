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

function array(value) {
  return Array.isArray(value) ? value : [];
}

function nums(questions) {
  return [...new Set(array(questions).map((q) => Number(q?.question_no)).filter(Number.isFinite))].sort((a, b) => a - b);
}

function hasMeaningfulVisualAsset(asset) {
  const role = `${asset?.role || ''} ${asset?.image_role || ''}`.toLowerCase();
  return /chart|table|figure|diagram|visual|question_visual|image/.test(role) &&
    !/question_stem|question_options/.test(role);
}

function meaningfulVisualAssets(question) {
  return array(question?.visual_assets).filter(hasMeaningfulVisualAsset);
}

function hasCompleteImageLinkage(question) {
  const meaningfulAssets = meaningfulVisualAssets(question);
  if (!meaningfulAssets.length) return question?.visual_summary === 'no_visual_context';
  return meaningfulAssets.every((asset) =>
    Boolean(
      asset?.asset_id &&
      Number(asset?.page) > 0 &&
      Array.isArray(asset?.bbox) &&
      asset.bbox.length === 4 &&
      typeof asset?.belongs_to_question === 'boolean' &&
      asset?.image_role &&
      asset?.linked_by &&
      asset?.link_reason &&
      asset?.visual_hash,
    ),
  );
}

function hasValue(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === 'string') return value.trim().length > 0;
  if (Array.isArray(value)) return true;
  return true;
}

function joinText(value) {
  if (Array.isArray(value)) return value.join('、');
  if (value === null || value === undefined) return '';
  return String(value);
}

function questionKey(question, index) {
  return String(question?.question_no ?? `idx-${index}`);
}

function firstVisualQuestion(questions) {
  return questions.find((question) => meaningfulVisualAssets(question).length > 0) || questions[0] || null;
}

function compareField(left, right) {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

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
  consistency: {},
  screenshots: [],
  errors: [],
  warnings: [],
};

let browser;
let apiCtx;

try {
  apiCtx = await request.newContext({ baseURL: backendBase });
  const token = await login(apiCtx);
  const [task, paper, debug] = await Promise.all([
    getJson(apiCtx, token, `/admin/pdf/task/${taskId}`),
    getJson(apiCtx, token, `/admin/pdf/task/${taskId}/paper-candidates`),
    getJson(apiCtx, token, `/admin/pdf/task/${taskId}/ai-preaudit-debug`),
  ]);

  await writeFile(path.join(outputDir, 'playwright-live-task-api.json'), JSON.stringify(task, null, 2) + '\n');
  await writeFile(path.join(outputDir, 'playwright-live-paper-candidates-api.json'), JSON.stringify(paper, null, 2) + '\n');
  await writeFile(path.join(outputDir, 'playwright-live-ai-preaudit-debug-api.json'), JSON.stringify(debug, null, 2) + '\n');

  const questions = array(paper.questions);
  const debugQuestions = array(debug.final_preview_payload?.questions);
  const debugAudits = array(debug.ai_audit_results);
  const questionNos = nums(questions);
  const debugByKey = new Map();
  const auditByKey = new Map();
  debugQuestions.forEach((question, index) => debugByKey.set(questionKey(question, index), question));
  debugAudits.forEach((item, index) => auditByKey.set(questionKey(item, index), item));

  const mismatches = [];
  for (const [index, question] of questions.entries()) {
    const key = questionKey(question, index);
    const debugQuestion = debugByKey.get(key) || {};
    const debugAudit = auditByKey.get(key) || {};
    const comparisonTargets = [
      ['ai_audit_status', question.ai_audit_status, debugAudit.ai_audit_status ?? debugQuestion.ai_audit_status],
      ['ai_audit_verdict', question.ai_audit_verdict, debugAudit.ai_audit_verdict ?? debugQuestion.ai_audit_verdict],
      ['ai_audit_summary', question.ai_audit_summary, debugAudit.ai_audit_summary ?? debugQuestion.ai_audit_summary],
      ['visual_summary', question.visual_summary, debugAudit.visual_summary ?? debugQuestion.visual_summary],
      ['visual_parse_status', question.visual_parse_status, debugAudit.visual_parse_status ?? debugQuestion.visual_parse_status],
      ['answer_suggestion', question.answer_suggestion, debugAudit.answer_suggestion ?? debugQuestion.answer_suggestion],
      ['answer_unknown_reason', question.answer_unknown_reason, debugAudit.answer_unknown_reason ?? debugQuestion.answer_unknown_reason],
      ['analysis_suggestion', question.analysis_suggestion, debugAudit.analysis_suggestion ?? debugQuestion.analysis_suggestion],
      ['analysis_unknown_reason', question.analysis_unknown_reason, debugAudit.analysis_unknown_reason ?? debugQuestion.analysis_unknown_reason],
      ['risk_flags', question.risk_flags || [], debugAudit.risk_flags ?? debugQuestion.risk_flags ?? []],
    ];
    for (const [field, left, right] of comparisonTargets) {
      if (!compareField(left, right)) {
        mismatches.push({ question_no: question.question_no, field, live: left ?? null, debug: right ?? null });
      }
    }
  }

  audit.api = {
    status: task.status,
    totalCount: task.total_count,
    doneCount: task.done_count,
    questionNos,
    questionCount: questions.length,
  };
  audit.coverage = {
    aiAuditStatusPresent: questions.filter((q) => hasValue(q.ai_audit_status)).length,
    aiAuditVerdictPresent: questions.filter((q) => hasValue(q.ai_audit_verdict)).length,
    aiAuditSummaryPresent: questions.filter((q) => hasValue(q.ai_audit_summary)).length,
    answerSuggestionPresent: questions.filter((q) => hasValue(q.answer_suggestion)).length,
    answerSuggestionOrReasonPresent: questions.filter((q) => hasValue(q.answer_suggestion) || hasValue(q.answer_unknown_reason)).length,
    analysisSuggestionPresent: questions.filter((q) => hasValue(q.analysis_suggestion)).length,
    analysisSuggestionOrReasonPresent: questions.filter((q) => hasValue(q.analysis_suggestion) || hasValue(q.analysis_unknown_reason)).length,
    visualSummaryPresent: questions.filter((q) => hasValue(q.visual_summary)).length,
    visualParseStatusPresent: questions.filter((q) => hasValue(q.visual_parse_status)).length,
    aiReviewedBeforeHumanTrue: questions.filter((q) => q.ai_reviewed_before_human === true).length,
    riskFlagsFieldPresent: questions.filter((q) => Array.isArray(q.risk_flags)).length,
    riskFlagsNonEmpty: questions.filter((q) => array(q.risk_flags).length > 0).length,
    withMeaningfulVisualAssets: questions.filter((q) => meaningfulVisualAssets(q).length > 0).length,
    imageLinkageComplete: questions.filter(hasCompleteImageLinkage).length,
  };
  audit.consistency = {
    debugLiveMismatchCount: mismatches.length,
    debugLiveConsistency: mismatches.length === 0 ? 'pass' : 'fail',
    mismatches,
  };
  audit.checks.m4ApiCoverage =
    audit.coverage.aiAuditStatusPresent === questions.length &&
    audit.coverage.aiAuditVerdictPresent === questions.length &&
    audit.coverage.aiAuditSummaryPresent === questions.length &&
    audit.coverage.answerSuggestionOrReasonPresent === questions.length &&
    audit.coverage.analysisSuggestionOrReasonPresent === questions.length &&
    audit.coverage.visualSummaryPresent === questions.length &&
    audit.coverage.visualParseStatusPresent === questions.length &&
    audit.coverage.aiReviewedBeforeHumanTrue === questions.length &&
    audit.coverage.riskFlagsFieldPresent === questions.length &&
    audit.coverage.imageLinkageComplete === questions.length;
  audit.checks.debugLiveConsistency = audit.consistency.debugLiveConsistency === 'pass';

  browser = await chromium.launch({
    headless: true,
    executablePath: chromeExecutablePath,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  await context.addInitScript((adminToken) => window.localStorage.setItem('admin_token', adminToken), token);
  const page = await context.newPage();
  page.on('console', (msg) => {
    if (!['error', 'warning'].includes(msg.type())) return;
    const entry = `console.${msg.type()}: ${msg.text()}`;
    if (/Failed to load resource:.*404/i.test(msg.text())) {
      audit.warnings.push(entry);
      return;
    }
    audit.errors.push(entry);
  });
  page.on('pageerror', (err) => audit.errors.push(`pageerror: ${err.message}`));

  await page.goto(`${adminBase}/pdf/tasks`, { waitUntil: 'networkidle', timeout: 30000 });
  audit.checks.adminWebReachable = true;
  await page.screenshot({ path: path.join(outputDir, 'admin-task-list.png'), fullPage: true });
  audit.screenshots.push(path.join(outputDir, 'admin-task-list.png'));

  await page.goto(`${adminBase}/pdf/tasks/${taskId}/paper-review`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.getByTestId('paper-review-overview').waitFor({ state: 'visible', timeout: 15000 });
  audit.checks.paperReviewReachable = true;

  const selectedQuestion = firstVisualQuestion(questions);
  if (selectedQuestion?.question_no) {
    const row = page.locator('button.candidate-row').filter({ hasText: `第 ${selectedQuestion.question_no} 题` }).first();
    if (await row.count()) {
      await row.click();
      await page.waitForTimeout(400);
    }
  }

  const bodyText = await page.locator('body').innerText();
  const visualSummaryText = await page.getByTestId('visual-summary-panel').innerText();
  const riskFlagText = await page.getByTestId('risk-flag-list').innerText();
  const linkageText = await page.getByTestId('image-linkage-list').innerText();
  const selectedPanelText = await page.getByTestId('candidate-selected').innerText();

  audit.ui = {
    bodyTextLength: bodyText.length,
    selectedQuestionNo: selectedQuestion?.question_no ?? null,
    visualSummaryText,
    riskFlagText,
    linkageText,
  };
  audit.checks.noUndefinedText = !/undefined/i.test(bodyText);
  audit.checks.noObjectObjectText = !/\[object Object\]/.test(bodyText);
  audit.checks.noVisualParseUnavailableText = !/visual parse unavailable/i.test(bodyText);
  audit.checks.aiStatusVisible = /AI\s+(passed|warning|failed|skipped)/i.test(selectedPanelText);
  audit.checks.visualSummaryVisible = visualSummaryText.trim().length > 0 && !/未提供视觉摘要/.test(visualSummaryText);
  audit.checks.answerVisible = /答案建议|答案原因|无答案建议|模型未给出可验证答案建议|缺失/.test(selectedPanelText);
  audit.checks.analysisVisible = /解析建议|解析原因|无解析建议|模型未给出可验证解析建议|缺失/.test(selectedPanelText);
  audit.checks.riskFlagsVisible = riskFlagText.trim().length > 0;
  audit.checks.imageLinkageVisible = linkageText.trim().length > 0 && !/未返回 image linkage/.test(linkageText);

  await page.screenshot({ path: path.join(outputDir, 'admin-paper-review.png'), fullPage: true });
  audit.screenshots.push(path.join(outputDir, 'admin-paper-review.png'));

  await context.tracing.stop({ path: path.join(outputDir, 'playwright-trace.zip') });
  await browser.close();
  browser = null;
  await apiCtx.dispose();
  apiCtx = null;
} catch (error) {
  audit.errors.push(error?.stack || error?.message || String(error));
  try { if (browser) await browser.close(); } catch {}
  try { if (apiCtx) await apiCtx.dispose(); } catch {}
}

const lines = [
  '# M4 Playwright/API/Admin UI Audit',
  `- task_id: ${taskId}`,
  `- checked_at: ${audit.checkedAt}`,
  `- question_count: ${audit.api.questionCount ?? 'n/a'}`,
  `- ai_audit_status_present: ${audit.coverage.aiAuditStatusPresent ?? 0}/${audit.api.questionCount ?? 0}`,
  `- ai_audit_summary_present: ${audit.coverage.aiAuditSummaryPresent ?? 0}/${audit.api.questionCount ?? 0}`,
  `- answer_suggestion_or_reason_present: ${audit.coverage.answerSuggestionOrReasonPresent ?? 0}/${audit.api.questionCount ?? 0}`,
  `- analysis_suggestion_or_reason_present: ${audit.coverage.analysisSuggestionOrReasonPresent ?? 0}/${audit.api.questionCount ?? 0}`,
  `- visual_summary_present: ${audit.coverage.visualSummaryPresent ?? 0}/${audit.api.questionCount ?? 0}`,
  `- image_linkage_complete: ${audit.coverage.imageLinkageComplete ?? 0}/${audit.api.questionCount ?? 0}`,
  `- debug_live_consistency: ${audit.consistency.debugLiveConsistency || 'fail'}`,
  '',
  '## Checks',
  ...Object.entries(audit.checks).map(([key, value]) => `- ${key}: ${value}`),
  '',
  '## Screenshots/trace',
  ...audit.screenshots.map((file) => `- ${file}`),
  `- ${path.join(outputDir, 'playwright-trace.zip')}`,
  '',
  '## Errors',
  ...(audit.errors.length ? audit.errors.map((entry) => `- ${entry}`) : ['- none']),
  '',
  '## Warnings',
  ...(audit.warnings.length ? audit.warnings.map((entry) => `- ${entry}`) : ['- none']),
  '',
];

await writeFile(path.join(outputDir, 'playwright-recognition-audit.json'), JSON.stringify(audit, null, 2) + '\n');
await writeFile(path.join(outputDir, 'PLAYWRIGHT_RECOGNITION_AUDIT_REPORT.md'), lines.join('\n'));
console.log(JSON.stringify({
  outputDir,
  checks: audit.checks,
  coverage: audit.coverage,
  consistency: audit.consistency,
  errors: audit.errors,
}, null, 2));

if (audit.errors.length || audit.checks.debugLiveConsistency === false || audit.checks.m4ApiCoverage === false) {
  process.exitCode = 2;
}
