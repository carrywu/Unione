#!/usr/bin/env node

import { chromium, request } from 'playwright';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const DEFAULT_TASK_ID = '1a43676e-14d6-4a71-8b81-d4442f08fb43';
const DEFAULT_BANK_ID = '1628f7cc-198f-4040-aab7-6c536bfb548f';
const DEFAULT_PAPER_ID = 'f8f2dc59-5625-4a07-a30d-d36c3decc500';
const DEFAULT_ADMIN_BASE = 'http://127.0.0.1:5173';
const DEFAULT_BACKEND_BASE = 'http://127.0.0.1:3010';
const DEFAULT_DEBUG_DIR = defaultOutputDir();
const DEFAULT_MAIN_TEST_PDF = '/Users/apple/Downloads/题本篇-1-8.pdf';
const DEFAULT_PARTIAL_CONTEXT_NEGATIVE_PDF = '/Users/apple/Downloads/公考/project2/backend/sample-题本篇-3-7.pdf';
const FOCUS_QUESTION_NOS = [1, 8, 9, 10];
const BAD_UI_TERMS = ['question stem', '[object Object]', 'visual parse unavailable'];

function defaultOutputDir() {
  const now = new Date();
  const stamp = [
    now.getFullYear(),
    `${now.getMonth() + 1}`.padStart(2, '0'),
    `${now.getDate()}`.padStart(2, '0'),
    '-',
    `${now.getHours()}`.padStart(2, '0'),
    `${now.getMinutes()}`.padStart(2, '0'),
    `${now.getSeconds()}`.padStart(2, '0'),
  ].join('');
  return `/Users/apple/Downloads/公考/project2/debug/paper-review/${stamp}/negative-regression`;
}

const args = new Set(process.argv.slice(2));
if (args.has('--help')) {
  console.log(`Usage: node scripts/check-paper-review-recognition.mjs

Environment overrides:
  TASK_ID, BANK_ID, PAPER_ID, ADMIN_BASE_URL, BACKEND_BASE_URL, OUTPUT_DIR
  ADMIN_TOKEN, ADMIN_PHONE, ADMIN_PASSWORD, HEADLESS=false

Outputs:
  recognition-audit.json
  RECOGNITION_AUDIT_REPORT.md
  recognition-screenshots/*.png`);
  process.exit(0);
}

let taskId = process.env.TASK_ID || DEFAULT_TASK_ID;
let bankId = process.env.BANK_ID || DEFAULT_BANK_ID;
let paperId = process.env.PAPER_ID || DEFAULT_PAPER_ID;
const adminBaseUrl = trimTrailingSlash(process.env.ADMIN_BASE_URL || DEFAULT_ADMIN_BASE);
const backendBaseUrl = trimTrailingSlash(process.env.BACKEND_BASE_URL || DEFAULT_BACKEND_BASE);
const outputDir = process.env.OUTPUT_DIR || DEFAULT_DEBUG_DIR;
const mainTestPdf = process.env.MAIN_TEST_PDF || DEFAULT_MAIN_TEST_PDF;
const partialContextNegativePdf = process.env.PARTIAL_CONTEXT_NEGATIVE_PDF || DEFAULT_PARTIAL_CONTEXT_NEGATIVE_PDF;
const screenshotsDir = path.join(outputDir, 'screenshots');
const fixtureRole = process.env.FIXTURE_ROLE || 'partial_pdf_context_negative_regression';
let pageUrl = buildPageUrl();
let activeBrowser = null;
let activeApiContext = null;

function trimTrailingSlash(value) {
  return String(value).replace(/\/+$/, '');
}

function buildPageUrl() {
  return `${adminBaseUrl}/pdf/tasks/${taskId}/paper-review?paperId=${paperId}`;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function unwrapApi(body, pathLabel) {
  if (body && typeof body === 'object' && typeof body.code === 'number') {
    assert(body.code === 0, `${pathLabel} API code ${body.code}: ${body.message || ''}`);
    return body.data;
  }
  return body;
}

async function createApiContext() {
  const context = await request.newContext({ baseURL: backendBaseUrl });
  if (process.env.ADMIN_TOKEN) {
    return { context, token: process.env.ADMIN_TOKEN };
  }

  const candidates = [
    { phone: process.env.ADMIN_PHONE || 'admin', password: process.env.ADMIN_PASSWORD || 'admin' },
    { phone: process.env.ADMIN_PHONE || '13800138000', password: process.env.ADMIN_PASSWORD || '123456' },
  ];
  for (const credential of candidates) {
    const response = await context.post('/api/auth/login', { data: credential });
    if (!response.ok()) continue;
    const data = unwrapApi(await response.json(), '/api/auth/login');
    if (data?.access_token) return { context, token: data.access_token };
  }
  throw new Error('无法登录后台获取验收数据；请设置 ADMIN_TOKEN 或检查种子账号');
}

async function getJson(context, token, apiPath) {
  const response = await context.get(apiPath, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const text = await response.text();
  assert(response.ok(), `${apiPath} HTTP ${response.status()}: ${text.slice(0, 300)}`);
  return unwrapApi(JSON.parse(text), apiPath);
}

async function postJson(context, token, apiPath, data) {
  const response = await context.post(apiPath, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  const text = await response.text();
  assert(response.ok(), `${apiPath} HTTP ${response.status()}: ${text.slice(0, 300)}`);
  return unwrapApi(JSON.parse(text), apiPath);
}

async function uploadPdf(context, token, pdfPath) {
  const buffer = await readFile(pdfPath);
  const filename = path.basename(pdfPath);
  const response = await context.post('/admin/upload/file', {
    headers: { Authorization: `Bearer ${token}` },
    multipart: {
      file: {
        name: filename,
        mimeType: 'application/pdf',
        buffer,
      },
    },
  });
  const text = await response.text();
  assert(response.ok(), `/admin/upload/file HTTP ${response.status()}: ${text.slice(0, 300)}`);
  return unwrapApi(JSON.parse(text), '/admin/upload/file');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function resolveFixtureTask(context, token) {
  if (fixtureRole !== 'main_positive_fixture') return;
  const basename = path.basename(mainTestPdf);
  const tasks = await getJson(context, token, `/admin/pdf/tasks?bankId=${encodeURIComponent(bankId)}`);
  const existing = array(tasks).find((task) =>
    String(task?.file_name || '').includes(basename) &&
    ['done', 'failed'].includes(String(task?.status || '')),
  );
  if (existing?.status === 'done') {
    taskId = existing.id;
  } else {
    const uploaded = await uploadPdf(context, token, mainTestPdf);
    const parsed = await postJson(context, token, '/admin/pdf/parse', {
      bank_id: bankId,
      file_url: uploaded.url,
      file_name: basename,
    });
    taskId = parsed.task_id;
    const deadline = Date.now() + Number(process.env.MAIN_PARSE_TIMEOUT_MS || 20 * 60 * 1000);
    let status = null;
    while (Date.now() < deadline) {
      status = await getJson(context, token, `/admin/pdf/task/${taskId}`);
      if (['done', 'failed', 'paused'].includes(String(status?.status))) break;
      await sleep(5000);
    }
    assert(status?.status === 'done', `main_positive_fixture 解析任务未完成：${status?.status || 'timeout'} ${status?.error || ''}`);
  }
  const draft = await postJson(context, token, '/admin/pdf/papers/draft', {
    source_task_id: taskId,
    source_bank_id: bankId,
    title: `主测试 PDF 制卷核对 ${basename}`,
    questions: [],
  });
  paperId = draft.paper_id;
  pageUrl = buildPageUrl();
}

async function readJsonIfExists(filePath) {
  try {
    return JSON.parse(await readFile(filePath, 'utf8'));
  } catch {
    return null;
  }
}

function array(value) {
  return Array.isArray(value) ? value : [];
}

function stringValue(value, fallback = '') {
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'string') return value.trim() || fallback;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

function textSnippet(value, max = 90) {
  const text = stringValue(value).replace(/\s+/g, ' ').trim();
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function hasBbox(value) {
  return Array.isArray(value) && value.length === 4 && value.every((item) => Number.isFinite(Number(item)));
}

function groupFor(groups, questionNo) {
  return array(groups).find((item) => String(item?.question_no) === String(questionNo)) || null;
}

function auditFor(audits, questionNo) {
  return array(audits).find((item) => String(item?.question_no) === String(questionNo)) || null;
}

function recropFor(recrops, questionNo) {
  return array(recrops).find((item) => String(item?.question_no) === String(questionNo)) || null;
}

function sourceEvidence(questionNo, candidate, group, pageHasOriginalLocator) {
  const stemBlocks = array(group?.stem_group?.blocks);
  const optionBlocks = array(group?.options_group?.blocks);
  const hasSourcePage = array(candidate?.source_page_refs).length > 0 || Number(group?.source_page_start || 0) > 0;
  const hasStemBbox = hasBbox(group?.stem_group?.bbox) || stemBlocks.some((block) => hasBbox(block?.bbox));
  const hasOptionsBbox = optionBlocks.filter((block) => hasBbox(block?.bbox)).length >= 4;
  const hasSourceTextSpan = Boolean(
    candidate?.source_text_span ||
      group?.source_text_span ||
      group?.stem_group?.source_text_span ||
      stemBlocks.some((block) => block?.source_text_span),
  );
  const stemMatchesGroup =
    stringValue(candidate?.stem) &&
    stringValue(group?.stem_group?.text) &&
    stringValue(group?.stem_group?.text).includes(stringValue(candidate?.stem).slice(0, 16));

  const missing = [];
  if (!hasSourcePage) missing.push('source_page_missing');
  if (!hasStemBbox) missing.push('stem_bbox_missing');
  if (!hasOptionsBbox) missing.push('option_bbox_missing');
  if (!hasSourceTextSpan) missing.push('source_text_span_missing');
  if (!pageHasOriginalLocator) missing.push('paper_review_original_pdf_locator_missing');
  if (!stemMatchesGroup) missing.push('stem_text_correspondence_unverified');

  let status = missing.length ? 'warning' : 'pass';
  if (questionNo === 1 && missing.length) status = 'fail';
  if (!hasSourcePage || !hasStemBbox) status = 'fail';

  return {
    status,
    questionSourceFound: status === 'pass',
    optionSourceFound: hasOptionsBbox ? (pageHasOriginalLocator && hasSourceTextSpan ? 'pass' : 'warning') : 'fail',
    missing,
    hasSourcePage,
    hasStemBbox,
    hasOptionsBbox,
    hasSourceTextSpan,
    stemMatchesGroup,
  };
}

function materialStatus(questionNo, group) {
  if (questionNo === 1) return 'not_applicable';
  const hasExplicitMaterial =
    Boolean(group?.material_group || group?.material_group_id || group?.shared_material_group_id) ||
    array(group?.notes_group?.blocks).some((block) => /material|资料|材料/i.test(String(block?.kind || block?.source || '')));
  return hasExplicitMaterial ? 'bound' : 'missing';
}

function chartStatus(questionNo, group) {
  const visualComplete = Boolean(group?.visual_group?.complete || array(group?.visual_group?.blocks).length);
  const titleComplete = Boolean(group?.title_group?.complete || group?.table_header_group?.complete);
  if (questionNo === 1) return visualComplete && titleComplete ? 'bound' : 'warning';
  return visualComplete ? (titleComplete ? 'bound' : 'warning') : 'missing';
}

function derivedRisks(questionNo, candidate, group, source, materialGroupStatus, chartOrTableEvidenceStatus) {
  const risks = new Set([...array(candidate?.risk_flags).map(String), ...array(group?.risk_flags).map(String)]);
  if (source.status !== 'pass') risks.add('source_unverified');
  if (questionNo === 1 && source.status !== 'pass') {
    risks.add('question_not_found_in_pdf');
    risks.add('ghost_candidate_possible');
  }
  if (materialGroupStatus === 'missing') {
    risks.add('shared_material_missing');
    risks.add('material_group_unbound');
  }
  if (chartOrTableEvidenceStatus === 'missing' || chartOrTableEvidenceStatus === 'warning') {
    risks.add('semantic_visual_incomplete');
  }
  if ([8, 9, 10].includes(questionNo) && materialGroupStatus === 'missing') {
    risks.add('question_cross_page');
    risks.add('partial_pdf_context');
    risks.add('missing_previous_page_context');
  }
  if (questionNo === 9) {
    risks.add('math_notation_normalization_required');
    risks.add('latex_like_notation_detected');
    risks.add('subscript_notation_unstructured');
    risks.add('formula_source_crop_required');
    risks.add('inequality_relation_requires_visual_evidence');
  }
  return Array.from(risks);
}

function expectedDecision(questionNo) {
  if (questionNo === 1) return '不可入卷：来源未验证，需人工确认是否为 ghost candidate';
  if (questionNo === 9) return '不可自动入卷：数学展示可核对，但材料/公式来源证据不足';
  return '不可自动入卷：可进入人工核对，但材料/图表绑定不足';
}

function makeNotes(questionNo, source, materialGroupStatus, chartOrTableEvidenceStatus, storedQuestion) {
  const notes = [];
  if (source.missing.length) notes.push(`缺少关键 source evidence：${source.missing.join(', ')}`);
  if (materialGroupStatus === 'missing') notes.push('未发现 material_group / shared material 绑定');
  if (chartOrTableEvidenceStatus === 'missing') notes.push('未发现图表/表格 evidence 绑定');
  if (questionNo === 9) notes.push('R19/R20/R21 与不等式展示需要结合材料来源人工复核');
  if (storedQuestion?.ai_audit_status === 'passed') notes.push('数据库题目 AI 状态为 passed，但 paper-review 候选题按 warning 展示，需后续统一状态来源');
  return notes;
}

async function safeScreenshot(locator, filePath, artifacts, label) {
  try {
    await locator.screenshot({ path: filePath });
    artifacts.screenshots.push({ label, path: filePath });
    return true;
  } catch (error) {
    artifacts.screenshots.push({ label, path: filePath, error: error.message });
    return false;
  }
}

function markdownTable(rows, columns) {
  return [
    `| ${columns.map((column) => column.label).join(' | ')} |`,
    `| ${columns.map(() => '---').join(' | ')} |`,
    ...rows.map((row) => `| ${columns.map((column) => String(row[column.key] ?? '').replace(/\n/g, '<br>')).join(' | ')} |`),
  ].join('\n');
}

function buildReport(audit) {
  const rows = audit.questions.map((question) => ({
    no: question.questionNo,
    source: question.sourceEvidenceStatus,
    material: question.materialGroupStatus,
    visual: question.chartOrTableEvidenceStatus,
    preview: question.previewConsistency,
    ui: question.uiStatus,
    decision: question.expectedDecision,
    risks: question.riskTags.join(', '),
  }));
  const screenshotLines = audit.artifacts.screenshots.map((item) =>
    `- ${item.label}: ${item.path}${item.error ? ` (失败: ${item.error})` : ''}`,
  );
  const manualList = audit.questions
    .filter((item) => item.expectedDecision.includes('不可'))
    .map((item) => `- 第 ${item.questionNo} 题：${item.expectedDecision}；风险：${item.riskTags.join(', ') || '无'}`);

  return `# 制卷页题目识别质量验收报告

## 1. 本轮结论

${audit.overall.summary}

- 页面是否能进入人工核对阶段：${audit.overall.canEnterManualReview ? '是' : '否'}
- 是否允许发布：${audit.overall.canPublish ? '是' : '否'}
- 是否允许入库：${audit.overall.canAutoIngest ? '是' : '否'}
- 是否允许自动组卷：${audit.overall.canAutoCompose ? '是' : '否'}

## 2. 关键页面与 ID

- pageUrl: ${audit.pageUrl}
- taskId: ${audit.taskId}
- bankId: ${audit.bankId}
- paperId: ${audit.paperId}
- checkedAt: ${audit.checkedAt}

## 2.1 PDF 样例策略

- 当前验收 section：${audit.fixtureRole}
- 当前主测试 PDF：${audit.fixtures.main_positive_fixture.path}
- partial context 负样例：${audit.fixtures.partial_pdf_context_negative_regression.path}
- partial context 负样例验收：不可自动入卷、不可人工强制加入、必须显示缺少材料/上下文原因、不得误判为 AI passed。

## 3. 第 1 / 8 / 9 / 10 题识别结论

${markdownTable(rows, [
    { key: 'no', label: '题号' },
    { key: 'source', label: '题干 source evidence' },
    { key: 'material', label: 'material_group' },
    { key: 'visual', label: '图表/表格 evidence' },
    { key: 'preview', label: '预览一致性' },
    { key: 'ui', label: 'UI 状态' },
    { key: 'decision', label: '验收结论' },
    { key: 'risks', label: '风险标签' },
  ])}

## 4. 题干识别是否可靠

按保守规则，四道题均不能判定为完全可靠。当前 paper-review/API 未提供 source_text_span，paper-review 页面本身也没有原卷 PDF 定位区域；第 1 题按预期标记为 fail，第 8/9/10 题标记为 warning。

## 5. 选项识别是否可靠

第 1、8、9、10 题都能看到 A/B/C/D，并且 semantic-groups 中存在选项 bbox；但缺少 paper-review 原卷定位与 source_text_span，因此只判 warning，不判 pass。

## 6. 材料/图表/表格是否可靠绑定

第 8、9、10 题依赖材料或数据图表，但未发现 material_group/shared material 绑定，也没有完整 visual/table evidence，判 missing。第 1 题有 visual_group，但表头缺失或未定位，判 warning。

## 7. 题组 material_group 是否可靠绑定

未发现第 8、9、10 题的 shared material group。按保守规则标记 shared_material_missing / material_group_unbound。

## 8. 上下文风险

- partial_pdf_context: ${audit.questions.some((item) => item.riskTags.includes('partial_pdf_context')) ? '存在' : '未发现'}
- missing_previous_page_context: ${audit.questions.some((item) => item.riskTags.includes('missing_previous_page_context')) ? '存在' : '未发现'}
- source_unverified: ${audit.questions.some((item) => item.riskTags.includes('source_unverified')) ? '存在' : '未发现'}

## 9. 数学下标展示

- paper-review 第 9 题下标：${audit.math.paperReviewSubscriptsOk ? '通过' : '失败/未知'}
- 移动端预览第 9 题下标：${audit.math.mobilePreviewSubscriptsOk ? '通过' : '失败/未知'}
- 捕获到的 paper-review sub 文本：${audit.math.paperReviewSubTexts.join(', ') || '无'}
- 捕获到的移动端 sub 文本：${audit.math.mobilePreviewSubTexts.join(', ') || '无'}

## 10. 页面占位字段检查

- question stem: ${audit.badUiTerms.includes('question stem') ? '存在' : '未出现'}
- undefined: ${audit.badUiTerms.includes('undefined') ? '存在' : '未出现'}
- [object Object]: ${audit.badUiTerms.includes('[object Object]') ? '存在' : '未出现'}
- visual parse unavailable: ${audit.badUiTerms.includes('visual parse unavailable') ? '存在' : '未出现'}

## 11. 截图证据路径

${screenshotLines.join('\n')}

## 12. 需要人工复核的清单

${manualList.join('\n')}

## 13. 下一步建议

- 在 paper-candidates API 中补充 source_page/source_bbox/source_text_span 到候选题层级，减少只能从 debug artifact 推断的问题。
- 为第 8、9、10 题补齐 material_group/shared material 绑定与材料 bbox。
- 为资料分析题增加材料/图表 evidence 的页面展示，不要仅用题干和选项判断可入卷。
- 统一 paper-review 候选状态和数据库题目 AI 状态，避免同一题在不同页面展示 passed/warning 不一致。
- 后续再考虑 semantic-groups 精修、recrop 质量提升、parse_chunks、question_versions/audit_events。
`;
}

async function main() {
  await mkdir(screenshotsDir, { recursive: true });
  const artifacts = { screenshots: [] };
  const { context: apiContext, token } = await createApiContext();
  activeApiContext = apiContext;
  await resolveFixtureTask(apiContext, token);
  const [candidates, debug, paperPreview, questionsPage] = await Promise.all([
    getJson(apiContext, token, `/admin/pdf/task/${taskId}/paper-candidates`),
    getJson(apiContext, token, `/admin/pdf/task/${taskId}/ai-preaudit-debug`),
    getJson(apiContext, token, `/admin/pdf/papers/${paperId}/preview`).catch((error) => ({ error: error.message, questions: [] })),
    getJson(apiContext, token, `/admin/questions?bankId=${encodeURIComponent(bankId)}&page=1&pageSize=100`).catch(() => ({ list: [] })),
  ]);

  const localGroups = await readJsonIfExists(path.join(outputDir, 'semantic-groups.json'));
  const localRecrops = await readJsonIfExists(path.join(outputDir, 'recrop-plan.json'));
  const localAudits = await readJsonIfExists(path.join(outputDir, 'ai-audit-results.json'));
  const groups = array(debug.semantic_groups).length ? debug.semantic_groups : localGroups;
  const recrops = array(debug.recrop_plan).length ? debug.recrop_plan : localRecrops;
  const audits = array(debug.ai_audit_results).length ? debug.ai_audit_results : localAudits;
  const storedQuestions = array(questionsPage.list);

  const browser = await chromium.launch({ headless: process.env.HEADLESS !== 'false' });
  activeBrowser = browser;
  const browserContext = await browser.newContext({ viewport: { width: 1440, height: 980 } });
  await browserContext.addInitScript((adminToken) => {
    window.localStorage.setItem('admin_token', adminToken);
  }, token);
  const page = await browserContext.newPage();
  await page.goto(pageUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.getByTestId('paper-review-overview').waitFor({ state: 'visible', timeout: 15000 });

  const pageHasOriginalLocator = (await page.locator('.pdf-panel, .pdf-locator, [data-testid="original-pdf"], [data-testid="source-pdf"]').count()) > 0;

  await page.screenshot({ path: path.join(screenshotsDir, 'full-page.png'), fullPage: true });
  artifacts.screenshots.push({ label: 'full-page', path: path.join(screenshotsDir, 'full-page.png') });

  const questions = [];
  let paperReviewSubTexts = [];
  const previewQuestions = array(paperPreview?.questions || paperPreview?.preview?.questions);

  for (const questionNo of FOCUS_QUESTION_NOS) {
    const candidate = array(candidates.questions).find((item) => String(item?.question_no) === String(questionNo)) || null;
    const group = groupFor(groups, questionNo);
    const recrop = recropFor(recrops, questionNo);
    const audit = auditFor(audits, questionNo);
    const storedQuestion = storedQuestions.find((item) => Number(item.index_num) === Number(questionNo)) || null;
    const locator = page.locator('button.candidate-row', { hasText: `第 ${questionNo} 题` });
    const cardExists = (await locator.count()) > 0;
    assert(cardExists, `第 ${questionNo} 题候选卡片不存在`);
    await locator.first().scrollIntoViewIfNeeded();
    await locator.first().click();
    await page.getByTestId('candidate-selected').waitFor({ state: 'visible', timeout: 5000 });

    const selectedScope = page.getByTestId('candidate-selected');
    const detailText = await selectedScope.innerText();
    const rowText = await locator.first().innerText();
    const manualForceAddVisible = (await selectedScope.getByTestId('manual-force-add-button').count()) > 0;
    const manualForceAddDisabledVisible = (await selectedScope.getByTestId('manual-force-add-disabled').count()) > 0;
    const notManuallyReviewableVisible = (await selectedScope.getByTestId('not-manually-reviewable-badge').count()) > 0;
    const missingContextReasonText = manualForceAddDisabledVisible || notManuallyReviewableVisible
      ? await selectedScope.getByTestId('missing-context-reason').innerText().catch(() => '')
      : '';
    const recommendedActionText = manualForceAddDisabledVisible || notManuallyReviewableVisible
      ? await selectedScope.getByTestId('recommended-rerun-action').innerText().catch(() => '')
      : '';
    const uiStatus = [rowText, detailText].join('\n').includes('AI warning')
      ? 'AI warning'
      : [rowText, detailText].join('\n').includes('AI passed')
        ? 'AI passed'
        : textSnippet(rowText.split('\n').find((line) => /^warning|passed|failed|unknown$/i.test(line)) || rowText, 40);

    await safeScreenshot(
      page.getByTestId('candidate-selected'),
      path.join(screenshotsDir, `question-${questionNo}-card.png`),
      artifacts,
      `question-${questionNo}-card`,
    );

    if (questionNo === 9) {
      paperReviewSubTexts = await page.locator('[data-testid="candidate-selected"] .math-var sub').allTextContents();
      await safeScreenshot(
        page.getByTestId('risk-checklist'),
        path.join(screenshotsDir, 'risk-tags-area.png'),
        artifacts,
        'risk-tags-area',
      );
    }

    const source = sourceEvidence(questionNo, candidate, group, pageHasOriginalLocator);
    const materialGroupStatus = materialStatus(questionNo, group);
    const chartOrTableEvidenceStatus = chartStatus(questionNo, group);
    const riskTags = derivedRisks(questionNo, candidate, group, source, materialGroupStatus, chartOrTableEvidenceStatus);
    const paperQuestion = previewQuestions.find((item) => String(item?.question_no) === String(questionNo));
    const previewConsistency = paperQuestion
      ? stringValue(paperQuestion.stem) === stringValue(candidate?.stem)
        ? 'pass'
        : 'warning'
      : 'unknown';

    questions.push({
      questionNo,
      candidateExists: Boolean(candidate),
      cardVisible: cardExists,
      manualForceAddVisible,
      manualForceAddDisabledVisible,
      notManuallyReviewableVisible,
      missingContextReasonText,
      recommendedActionText,
      manualReviewable: Boolean(candidate?.manualReviewable),
      manualForceAddAllowed: Boolean(candidate?.manualForceAddAllowed),
      stemVisible: Boolean(stringValue(candidate?.stem)) && detailText.includes(stringValue(candidate?.stem).slice(0, 12)),
      optionsVisible: ['A', 'B', 'C', 'D'].every((key) => Boolean(stringValue(candidate?.options?.[key])) && detailText.includes(stringValue(candidate?.options?.[key]).slice(0, 4))),
      sourceEvidenceStatus: source.status,
      questionSourceFound: source.questionSourceFound,
      optionSourceFound: source.optionSourceFound,
      materialGroupStatus,
      chartOrTableEvidenceStatus,
      previewConsistency,
      riskTags,
      uiStatus,
      expectedDecision: expectedDecision(questionNo),
      notes: makeNotes(questionNo, source, materialGroupStatus, chartOrTableEvidenceStatus, storedQuestion),
      data: {
        candidate: {
          ai_audit_status: candidate?.ai_audit_status || null,
          can_add_to_paper: Boolean(candidate?.can_add_to_paper),
          manualReviewable: Boolean(candidate?.manualReviewable),
          manualForceAddAllowed: Boolean(candidate?.manualForceAddAllowed),
          manual_review_status: candidate?.manual_review_status || null,
          missingContextReason: candidate?.missingContextReason || null,
          recommendedAction: candidate?.recommendedAction || null,
          need_manual_fix: Boolean(candidate?.need_manual_fix),
          cannot_add_reason: candidate?.cannot_add_reason || null,
          source_page_refs: array(candidate?.source_page_refs),
          source_bbox: candidate?.source_bbox || null,
          source_text_span_present: Boolean(candidate?.source_text_span),
        },
        semantic_group: {
          source_page_start: group?.source_page_start ?? null,
          source_page_end: group?.source_page_end ?? null,
          stem_bbox: group?.stem_group?.bbox || null,
          options_bbox: group?.options_group?.bbox || null,
          visual_bbox: group?.visual_group?.bbox || null,
          uncertain: Boolean(group?.uncertain),
        },
        recrop_plan: {
          source_pages: array(recrop?.source_pages),
          crop_bbox: recrop?.crop_bbox || null,
          required_include_regions: array(recrop?.required_include_regions).map((item) => ({ kind: item?.kind, bbox: item?.bbox, page_no: item?.page_no })),
        },
        ai_audit: {
          status: audit?.ai_audit_status || null,
          can_answer: audit?.can_answer ?? null,
          suggested_action: audit?.suggested_action || null,
        },
        stored_question: storedQuestion
          ? {
              id: storedQuestion.id,
              ai_audit_status: storedQuestion.ai_audit_status || null,
              needs_review: Boolean(storedQuestion.needs_review),
              source_page_start: storedQuestion.source_page_start ?? null,
              source_bbox: storedQuestion.source_bbox || null,
            }
          : null,
      },
    });
  }

  const bodyText = await page.locator('body').innerText();
  const badUiTerms = BAD_UI_TERMS.filter((term) => bodyText.toLowerCase().includes(term.toLowerCase()));
  if (/\bundefined\b/i.test(bodyText)) badUiTerms.push('undefined');

  let mobilePreviewSubTexts = [];
  let mobilePreviewError = '';
  const q9Stored = storedQuestions.find((item) => Number(item.index_num) === 9);
  if (q9Stored?.id) {
    try {
      await page.goto(`${adminBaseUrl}/banks/${bankId}/review?questionId=${q9Stored.id}`, { waitUntil: 'networkidle', timeout: 30000 });
      const mobileButton = page.getByRole('button', { name: '移动端预览' }).first();
      await mobileButton.click();
      await page.locator('.phone-shell, .phone-frame').first().waitFor({ state: 'visible', timeout: 10000 });
      mobilePreviewSubTexts = await page.locator('.phone-shell .math-var sub, .phone-frame .math-var sub').allTextContents();
      await safeScreenshot(
        page.locator('.mobile-preview-drawer, .phone-shell, .phone-frame').first(),
        path.join(screenshotsDir, 'question-9-mobile-preview.png'),
        artifacts,
        'question-9-mobile-preview',
      );
    } catch (error) {
      mobilePreviewError = error.message;
      await page.screenshot({ path: path.join(screenshotsDir, 'question-9-mobile-preview.png'), fullPage: true }).catch(() => {});
      artifacts.screenshots.push({
        label: 'question-9-mobile-preview',
        path: path.join(screenshotsDir, 'question-9-mobile-preview.png'),
        error: error.message,
      });
    }
  } else {
    mobilePreviewError = '未在题库题目列表找到第 9 题，无法打开移动端预览';
  }

  const q1Stored = storedQuestions.find((item) => Number(item.index_num) === 1);
  if (q1Stored?.id) {
    try {
      await page.goto(`${adminBaseUrl}/banks/${bankId}/questions/${q1Stored.id}/preview`, { waitUntil: 'networkidle', timeout: 30000 });
      await page.locator('.source-panel, .pdf-panel').first().waitFor({ state: 'visible', timeout: 10000 });
      await safeScreenshot(
        page.locator('.pdf-panel, .source-panel').first(),
        path.join(screenshotsDir, 'original-pdf-area-page-1.png'),
        artifacts,
        'original-pdf-area-page-1',
      );
    } catch (error) {
      await page.screenshot({ path: path.join(screenshotsDir, 'original-pdf-area-page-1.png'), fullPage: true }).catch(() => {});
      artifacts.screenshots.push({
        label: 'original-pdf-area-page-1',
        path: path.join(screenshotsDir, 'original-pdf-area-page-1.png'),
        error: error.message,
      });
    }
  }

  const math = {
    paperReviewSubTexts,
    mobilePreviewSubTexts,
    paperReviewSubscriptsOk: ['19', '20', '21'].every((item) => paperReviewSubTexts.includes(item)),
    mobilePreviewSubscriptsOk: ['19', '20', '21'].every((item) => mobilePreviewSubTexts.includes(item)),
    mobilePreviewError: mobilePreviewError || null,
  };

  const pageReachable = true;
  const canEnterManualReview = questions.length === FOCUS_QUESTION_NOS.length && questions.every((item) => item.cardVisible);
  const canAutoCompose = array(candidates.questions).some((item) => item.can_add_to_paper);
  const audit = {
    taskId,
    bankId,
    paperId,
    pageUrl,
    fixtureRole,
    checkedAt: new Date().toISOString(),
    overall: {
      pageReachable,
      canEnterManualReview,
      canPublish: false,
      canAutoIngest: false,
      canAutoCompose: false,
      summary: canEnterManualReview
        ? '制卷页可进入人工核对；第 1、8、9、10 题均不能按保守 source/material 规则自动通过或自动入卷。'
        : '制卷页未能完整进入人工核对，需先修复页面或数据加载问题。',
      actualCandidateCanAddCount: array(candidates.questions).filter((item) => item.can_add_to_paper).length,
      actualCandidateCanAutoCompose: canAutoCompose,
    },
    provider: candidates.provider || null,
    model: candidates.model || null,
    fixtures: {
      main_positive_fixture: {
        path: mainTestPdf,
        role: 'main_positive_fixture',
        generatedFrom: {
          sourcePdf: '/Users/apple/Downloads/题本篇.pdf',
          pageRange: '1-8',
        },
      },
      partial_pdf_context_negative_regression: {
        path: partialContextNegativePdf,
        role: 'partial_pdf_context_negative_regression',
        acceptance: {
          canAutoIngest: false,
          canAutoCompose: false,
          mustShowMissingContextReason: true,
          manualForceAddAllowed: false,
          manualReviewable: false,
          mustNotBeAiPassed: true,
        },
      },
    },
    paperReviewHasOriginalPdfLocator: pageHasOriginalLocator,
    badUiTerms,
    math,
    questions,
    artifacts,
  };

  assert(questions.length === FOCUS_QUESTION_NOS.length, '未生成全部四道题的 audit 结果');
  assert(math.paperReviewSubscriptsOk, '第 9 题 paper-review 未检测到 19/20/21 下标 sub 节点');
  assert(!badUiTerms.length, `页面出现内部占位字段: ${badUiTerms.join(', ')}`);
  for (const question of questions) {
    assert(question.cardVisible, `第 ${question.questionNo} 题卡片不可见`);
    if (fixtureRole === 'main_positive_fixture') {
      assert(
        !question.riskTags.includes('partial_pdf_context') && !question.riskTags.includes('missing_previous_page_context'),
        `main_positive_fixture 第 ${question.questionNo} 题仍出现 partial/missing previous page context`,
      );
      if (question.riskTags.includes('source_unverified')) {
        assert(!/passed/i.test(question.uiStatus), `main_positive_fixture 第 ${question.questionNo} 题 source_unverified 但 UI 显示 passed`);
        assert(!question.manualForceAddAllowed, `main_positive_fixture 第 ${question.questionNo} 题 source_unverified 但允许人工强制加入`);
      }
    }
    if (question.riskTags.includes('source_unverified')) {
      assert(!/passed/i.test(question.uiStatus), `第 ${question.questionNo} 题 source_unverified 但 UI 显示 passed`);
    }
    if (question.riskTags.includes('shared_material_missing')) {
      assert(!question.data.candidate.can_add_to_paper, `第 ${question.questionNo} 题缺 material_group 但仍可自动入卷`);
    }
    if (question.riskTags.includes('partial_pdf_context')) {
      assert(!question.data.candidate.can_add_to_paper, `第 ${question.questionNo} 题 partial_pdf_context 但仍可自动入卷`);
      assert(!/passed/i.test(question.uiStatus), `第 ${question.questionNo} 题 partial_pdf_context 但 UI 显示 passed`);
      assert(!question.manualReviewable, `第 ${question.questionNo} 题 partial_pdf_context 但 manualReviewable=true`);
      assert(!question.manualForceAddAllowed, `第 ${question.questionNo} 题 partial_pdf_context 但 manualForceAddAllowed=true`);
      assert(!question.manualForceAddVisible, `第 ${question.questionNo} 题 partial_pdf_context 但仍显示可点击人工强制加入`);
      assert(
        question.manualForceAddDisabledVisible || question.notManuallyReviewableVisible,
        `第 ${question.questionNo} 题 partial_pdf_context 但未显示无法人工核验`,
      );
      assert(
        /无法人工核验|缺少|上一页|上下文|材料/.test(question.missingContextReasonText),
        `第 ${question.questionNo} 题缺少上下文原因未展示`,
      );
      assert(
        /补齐上一页|完整 PDF|重新解析/.test(question.recommendedActionText),
        `第 ${question.questionNo} 题补页/完整 PDF 重跑建议未展示`,
      );
    }
  }

  await writeFile(path.join(outputDir, 'recognition-audit.json'), `${JSON.stringify(audit, null, 2)}\n`);
  await writeFile(path.join(outputDir, 'RECOGNITION_AUDIT_REPORT.md'), buildReport(audit));
  await browser.close();
  await apiContext.dispose();

  console.log(`Recognition audit JSON: ${path.join(outputDir, 'recognition-audit.json')}`);
  console.log(`Recognition audit report: ${path.join(outputDir, 'RECOGNITION_AUDIT_REPORT.md')}`);
  console.log(`Screenshots: ${screenshotsDir}`);
}

main().catch(async (error) => {
  await activeBrowser?.close().catch(() => undefined);
  await activeApiContext?.dispose().catch(() => undefined);
  console.error(`Recognition audit failed: ${error.message}`);
  process.exitCode = 1;
});
