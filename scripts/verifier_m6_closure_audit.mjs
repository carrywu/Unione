#!/usr/bin/env node
import { chromium, devices, request } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const taskId = process.env.TASK_ID || '836fec20-2628-44ed-9642-aedd57467864';
const backendBase = (process.env.BACKEND_BASE_URL || 'http://127.0.0.1:3010').replace(/\/+$/, '');
const adminBase = (process.env.ADMIN_BASE_URL || 'http://127.0.0.1:5173').replace(/\/+$/, '');
const h5Base = (process.env.H5_BASE_URL || 'http://127.0.0.1:5174').replace(/\/+$/, '');
const chromeExecutablePath = process.env.CHROME_EXECUTABLE_PATH || '/usr/bin/google-chrome';
const m6Dir = process.env.M6_OUTPUT_DIR || path.join(process.cwd(), 'debug', 'm6', taskId);
const h5Dir = process.env.H5_OUTPUT_DIR || path.join(process.cwd(), 'debug', 'h5-regression', taskId);
const screenshotDir = path.join(m6Dir, 'screenshots');

function unwrap(body, label) {
  if (body && typeof body === 'object' && typeof body.code === 'number') {
    if (body.code !== 0) {
      throw new Error(`${label} API code=${body.code} message=${body.message || ''}`);
    }
    return body.data;
  }
  return body;
}

function array(value) {
  return Array.isArray(value) ? value : [];
}

function normText(value) {
  const text = String(value ?? '')
    .replace(/\s+/g, ' ')
    .replace(/\u00a0/g, ' ')
    .trim();
  return /^(unknown|none|null|n\/a|na)$/i.test(text) ? '' : text;
}

function optionMapFromQuestion(question) {
  return {
    A: normText(question?.option_a || question?.options?.A || ''),
    B: normText(question?.option_b || question?.options?.B || ''),
    C: normText(question?.option_c || question?.options?.C || ''),
    D: normText(question?.option_d || question?.options?.D || ''),
  };
}

function previewQuestionToComparable(question) {
  const answer = normText(question?.answer || '');
  const analysis = normText(question?.analysis || '');
  return {
    question_no: Number(question?.question_no),
    stem: normText(question?.content),
    options: optionMapFromQuestion(question),
    material: normText(question?.material?.content || ''),
    answer,
    analysis,
    answer_unknown_reason: answer ? '' : normText(question?.answer_unknown_reason || ''),
    analysis_unknown_reason: analysis ? '' : normText(question?.analysis_unknown_reason || ''),
    visual_summary: normText(question?.visual_summary || ''),
    image_asset_ids: array(question?.images).map((item) => normText(item?.asset_id || item?.ref || item?.id || item?.url || item?.src)),
  };
}

function candidateToComparable(question) {
  const answer = normText(
    question?.answer_override ||
      question?.final_answer_suggestion ||
      question?.answer_suggestion ||
      question?.answer ||
      '',
  );
  const analysis = normText(
    question?.analysis_override ||
      question?.final_analysis_suggestion ||
      question?.analysis_suggestion ||
      question?.analysis ||
      '',
  );
  return {
    question_no: Number(question?.question_no),
    stem: normText(question?.stem),
    options: {
      A: normText(question?.options?.A || ''),
      B: normText(question?.options?.B || ''),
      C: normText(question?.options?.C || ''),
      D: normText(question?.options?.D || ''),
    },
    material: normText(question?.material?.content || ''),
    answer,
    analysis,
    answer_unknown_reason: answer ? '' : normText(question?.answer_unknown_reason || ''),
    analysis_unknown_reason: analysis ? '' : normText(question?.analysis_unknown_reason || ''),
    visual_summary: normText(question?.visual_summary || ''),
    image_asset_ids: array(question?.visual_assets).map((item) => normText(item?.asset_id || item?.ref || item?.id || item?.url || item?.src)),
  };
}

function compareComparable(expected, actual) {
  const mismatches = [];
  for (const field of ['question_no', 'stem', 'material', 'answer', 'analysis', 'answer_unknown_reason', 'analysis_unknown_reason', 'visual_summary']) {
    if (JSON.stringify(expected[field] ?? null) !== JSON.stringify(actual[field] ?? null)) {
      mismatches.push({ field, expected: expected[field] ?? null, actual: actual[field] ?? null });
    }
  }
  for (const label of ['A', 'B', 'C', 'D']) {
    if (JSON.stringify(expected.options?.[label] ?? '') !== JSON.stringify(actual.options?.[label] ?? '')) {
      mismatches.push({
        field: `options.${label}`,
        expected: expected.options?.[label] ?? '',
        actual: actual.options?.[label] ?? '',
      });
    }
  }
  if (JSON.stringify(expected.image_asset_ids || []) !== JSON.stringify(actual.image_asset_ids || [])) {
    mismatches.push({
      field: 'image_asset_ids',
      expected: expected.image_asset_ids || [],
      actual: actual.image_asset_ids || [],
    });
  }
  return mismatches;
}

async function loginAdmin(apiCtx) {
  for (const cred of [
    { phone: process.env.ADMIN_PHONE || 'admin', password: process.env.ADMIN_PASSWORD || 'admin' },
    { phone: process.env.ADMIN_PHONE || '13800138000', password: process.env.ADMIN_PASSWORD || '123456' },
  ]) {
    const res = await apiCtx.post('/api/auth/login', { data: cred });
    if (!res.ok()) continue;
    const data = unwrap(await res.json(), '/api/auth/login');
    if (data?.access_token) return data.access_token;
  }
  throw new Error('admin login failed');
}

async function loginH5(apiCtx) {
  const res = await apiCtx.post('/api/auth/login', {
    data: {
      phone: process.env.H5_PHONE || '13900139000',
      password: process.env.H5_PASSWORD || '123456',
    },
  });
  if (!res.ok()) throw new Error(`h5 login failed: HTTP ${res.status()}`);
  const data = unwrap(await res.json(), '/api/auth/login');
  if (!data?.access_token) throw new Error('h5 login missing access_token');
  return data.access_token;
}

async function getJson(apiCtx, token, apiPath, label = apiPath) {
  const res = await apiCtx.get(apiPath, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const text = await res.text();
  if (!res.ok()) {
    throw new Error(`${label} HTTP ${res.status()}: ${text.slice(0, 500)}`);
  }
  return unwrap(JSON.parse(text), label);
}

async function getJsonWithRetry(apiCtx, token, apiPath, options = {}) {
  const {
    attempts = 8,
    delayMs = 500,
    label = apiPath,
  } = options;
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await getJson(apiCtx, token, apiPath, label);
    } catch (error) {
      lastError = error;
      if (!/HTTP 404/.test(String(error?.message || '')) || attempt === attempts) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  throw lastError || new Error(`retry exhausted: ${label}`);
}

async function postJson(apiCtx, token, apiPath, data, label = apiPath) {
  const res = await apiCtx.post(apiPath, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  const text = await res.text();
  if (!res.ok()) {
    throw new Error(`${label} HTTP ${res.status()}: ${text.slice(0, 500)}`);
  }
  return unwrap(JSON.parse(text), label);
}

async function saveJson(filePath, payload) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, JSON.stringify(payload, null, 2) + '\n');
}

async function clickOptionForAnswer(page, answer, questionType) {
  const buttons = page.locator('.options-list .option-card');
  const count = await buttons.count();
  if (count === 0) throw new Error('no option buttons found');
  const indexByAnswer =
    questionType === 'judge'
      ? { T: 0, F: 1 }
      : { A: 0, B: 1, C: 2, D: 3 };
  const targetIndex = indexByAnswer[answer] ?? 0;
  await buttons.nth(Math.min(targetIndex, count - 1)).click();
}

async function extractDomQuestion(page) {
  const stem = normText(await page.locator('.question-stem').innerText().catch(() => ''));
  const numberText = normText(await page.locator('.question-num').innerText().catch(() => ''));
  const material = normText(await page.locator('.material-text').innerText().catch(() => ''));
  const answer = normText(await page.locator('.analysis-answer').innerText().catch(() => ''));
  const analysis = normText(await page.locator('.analysis-text').innerText().catch(() => ''));
  const options = {};
  const optionCards = page.locator('.options-list .option-card');
  const optionCount = await optionCards.count();
  for (let index = 0; index < optionCount; index += 1) {
    const card = optionCards.nth(index);
    const letter = normText(await card.locator('.option-letter').innerText().catch(() => ''));
    const label = normText(await card.locator('.option-label').innerText().catch(() => ''));
    if (letter) options[letter] = label;
  }
  const imageStats = await page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    return Array.from(document.querySelectorAll('img')).map((image) => {
      const rect = image.getBoundingClientRect();
      return {
        src: image.getAttribute('src') || '',
        width: rect.width,
        height: rect.height,
        overflow: rect.width > viewportWidth + 1,
      };
    });
  });
  return {
    number_text: numberText,
    stem,
    material,
    options,
    answer,
    analysis,
    image_stats: imageStats,
  };
}

async function main() {
  await mkdir(m6Dir, { recursive: true });
  await mkdir(h5Dir, { recursive: true });
  await mkdir(screenshotDir, { recursive: true });

  const apiCtx = await request.newContext({ baseURL: backendBase });
  const adminToken = await loginAdmin(apiCtx);
  const h5Token = await loginH5(apiCtx);

  const [task, paperCandidates, debug] = await Promise.all([
    getJson(apiCtx, adminToken, `/admin/pdf/task/${taskId}`),
    getJson(apiCtx, adminToken, `/admin/pdf/task/${taskId}/paper-candidates`),
    getJson(apiCtx, adminToken, `/admin/pdf/task/${taskId}/ai-preaudit-debug`),
  ]);
  const consistencyPreview = await postJson(
    apiCtx,
    adminToken,
    `/admin/pdf/task/${taskId}/h5-consistency-preview`,
    { reason: 'M6B consistency preview from managed mode' },
  );

  const adminAudit = {
    task_id: taskId,
    checked_at: new Date().toISOString(),
    task_status: task.status,
    candidate_count: array(paperCandidates.questions).length,
    actions: [],
    checks: {},
    warnings: [],
    errors: [],
    screenshots: [],
  };
  const publishSmoke = {
    task_id: taskId,
    checked_at: new Date().toISOString(),
    checks: {},
    warnings: [],
    errors: [],
    screenshots: [],
  };
  const h5Audit = {
    task_id: taskId,
    checked_at: new Date().toISOString(),
    preview_paper_id: consistencyPreview.paper_id,
    preview_route: consistencyPreview.preview_route,
    question_count: consistencyPreview.question_count,
    mobile_smoke: [],
    failed_questions: [],
    warnings: [],
    screenshots: [],
  };

  const addableCandidate = array(paperCandidates.questions).find((question) => question.can_add_to_paper) || array(paperCandidates.questions)[0];
  const visualCandidate = array(paperCandidates.questions).find((question) => array(question.visual_assets).length > 0) || addableCandidate;

  const browser = await chromium.launch({
    headless: true,
    executablePath: chromeExecutablePath,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });

  try {
    const adminContext = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    await adminContext.tracing.start({ screenshots: true, snapshots: true, sources: true });
    await adminContext.addInitScript((token) => window.localStorage.setItem('admin_token', token), adminToken);
    const adminPage = await adminContext.newPage();
    adminPage.on('console', (msg) => {
      if (!['error', 'warning'].includes(msg.type())) return;
      adminAudit.warnings.push(`console.${msg.type()}: ${msg.text()}`);
    });
    adminPage.on('pageerror', (error) => adminAudit.errors.push(`pageerror: ${error.message}`));

    await adminPage.goto(`${adminBase}/pdf/tasks/${taskId}/paper-review`, {
      waitUntil: 'networkidle',
      timeout: 30000,
    });
    await adminPage.getByTestId('paper-review-overview').waitFor({ state: 'visible', timeout: 15000 });

    const overviewText = normText(await adminPage.getByTestId('paper-review-overview').innerText());
    const bodyText = normText(await adminPage.locator('body').innerText());
    adminAudit.checks.overviewVisible = overviewText.includes(taskId);
    adminAudit.checks.noUndefined = !/\bundefined\b/i.test(bodyText);
    adminAudit.checks.noObjectObject = !/\[object Object\]/.test(bodyText);
    adminAudit.checks.noVisualParseUnavailable = !/visual parse unavailable/i.test(bodyText);

    if (addableCandidate?.question_no) {
      const row = adminPage.locator('button.candidate-row').filter({ hasText: `第 ${addableCandidate.question_no} 题` }).first();
      await row.click();
      await adminPage.waitForTimeout(400);
    }

    adminAudit.checks.visualSummaryVisible = await adminPage.getByTestId('visual-summary-panel').isVisible();
    adminAudit.checks.answerBookPanelVisible = await adminPage.getByTestId('answer-book-panel').isVisible();
    adminAudit.checks.similarityPanelVisible = await adminPage.getByTestId('similarity-panel').isVisible();
    adminAudit.checks.auditLogPanelVisible = await adminPage.getByTestId('audit-log-panel').isVisible();

    await adminPage.getByPlaceholder('填写人工决策原因 / 证据摘要').fill('M6A managed review closure smoke');

    const acceptButton = adminPage.getByTestId('accept-match-button');
    if (await acceptButton.isEnabled().catch(() => false)) {
      await acceptButton.click();
      await adminPage.waitForTimeout(500);
      adminAudit.actions.push('accept_match');
    }

    const ignoreButton = adminPage.getByTestId('ignore-similarity-button');
    if (await ignoreButton.isVisible().catch(() => false)) {
      await ignoreButton.click();
      await adminPage.waitForTimeout(500);
      adminAudit.actions.push('ignore_similarity');
    }

    const approveButton = adminPage.getByTestId('approve-for-publish-button');
    if (await approveButton.isVisible().catch(() => false)) {
      await approveButton.click();
      await adminPage.waitForTimeout(500);
      adminAudit.actions.push('approve_for_publish');
    }

    const addToDraftButton = adminPage.getByRole('button', { name: '加入试卷' });
    if (await addToDraftButton.isEnabled().catch(() => false)) {
      await addToDraftButton.click();
      await adminPage.waitForTimeout(300);
      adminAudit.actions.push('add_to_draft');
    }

    await adminPage.getByRole('button', { name: '保存草稿' }).click();
    await adminPage.waitForTimeout(1200);
    const paperId = new URL(adminPage.url()).searchParams.get('paperId');
    if (!paperId) throw new Error('paperId missing after save draft');
    adminAudit.paper_id = paperId;

    await adminPage.getByRole('button', { name: 'Preview 发布' }).click();
    await adminPage.waitForTimeout(1200);
    adminAudit.actions.push('publish_preview');

    const previewPublishPanel = adminPage.getByTestId('preview-publish-panel');
    await previewPublishPanel.waitFor({ state: 'visible', timeout: 15000 });
    const auditLogText = normText(await adminPage.getByTestId('audit-log-panel').innerText());
    adminAudit.checks.auditLogHasAction = /accept_match|approve_for_publish|publish_preview/i.test(auditLogText);
    adminAudit.preview_publish_text = normText(await previewPublishPanel.innerText());

    const adminShot = path.join(screenshotDir, 'admin-review.png');
    await adminPage.screenshot({ path: adminShot, fullPage: true });
    adminAudit.screenshots.push(adminShot);

    for (const question of array(paperCandidates.questions)) {
      const questionNo = Number(question.question_no);
      if (!Number.isFinite(questionNo)) continue;
      const label = `第 ${questionNo} 题`;
      const row = adminPage.locator('button.candidate-row').filter({ hasText: label }).first();
      if (await row.count()) {
        await row.click();
        await adminPage.waitForTimeout(250);
      }
      const sourceShot = path.join(h5Dir, `q${String(questionNo).padStart(2, '0')}-source.png`);
      await adminPage.getByTestId('candidate-selected').screenshot({ path: sourceShot });
      if (await adminPage.locator('.visual-preview').count()) {
        const recropShot = path.join(h5Dir, `q${String(questionNo).padStart(2, '0')}-recrop.png`);
        await adminPage.locator('.visual-preview').first().screenshot({ path: recropShot }).catch(() => {});
      }
      await saveJson(
        path.join(h5Dir, `q${String(questionNo).padStart(2, '0')}-final-question.json`),
        question,
      );
    }

    await adminContext.tracing.stop({ path: path.join(m6Dir, 'trace.zip') });

    const reviewState = await getJson(apiCtx, adminToken, `/admin/pdf/task/${taskId}/review-state`);
    const publishPreviewMeta = reviewState.publish_preview || null;
    adminAudit.review_state = reviewState;
    adminAudit.publish_preview = publishPreviewMeta;

    if (!publishPreviewMeta?.paper_id) {
      throw new Error('review-state missing publish_preview.paper_id after admin flow');
    }

    const h5Context = await browser.newContext({
      ...devices['iPhone 13'],
      viewport: { width: 390, height: 844 },
    });
    await h5Context.addInitScript((token) => window.localStorage.setItem('h5_token', token), h5Token);
    const h5Page = await h5Context.newPage();
    h5Page.on('console', (msg) => {
      if (['error', 'warning'].includes(msg.type())) {
        h5Audit.warnings.push(`console.${msg.type()}: ${msg.text()}`);
      }
    });
    h5Page.on('pageerror', (error) => h5Audit.failed_questions.push({ question_no: 'page', error: error.message }));

    const consistencyPaper = await getJsonWithRetry(
      apiCtx,
      h5Token,
      `/api/preview-papers/${consistencyPreview.paper_id}`,
    );
    const consistencyByNo = new Map(
      array(consistencyPaper.questions).map((question) => [Number(question.question_no), question]),
    );
    const candidateByNo = new Map(
      array(paperCandidates.questions).map((question) => [Number(question.question_no), question]),
    );

    await h5Page.goto(`${h5Base}${consistencyPreview.preview_route}`, {
      waitUntil: 'networkidle',
      timeout: 30000,
    });
    await h5Page.locator('.question-stem').waitFor({ state: 'visible', timeout: 15000 });

    for (const [index, previewQuestion] of array(consistencyPaper.questions).entries()) {
      const questionNo = Number(previewQuestion.question_no);
      const currentNumberText = normText(await h5Page.locator('.question-num').innerText().catch(() => ''));
      if (!currentNumberText.includes(`${index + 1}`)) {
        h5Audit.warnings.push(`question ${questionNo}: question-num text=${currentNumberText}`);
      }

      const bodySnapshot = normText(await h5Page.locator('body').innerText());
      if (/\bundefined\b/i.test(bodySnapshot) || /\[object Object\]/.test(bodySnapshot) || /visual parse unavailable/i.test(bodySnapshot)) {
        h5Audit.failed_questions.push({
          question_no: questionNo,
          field: 'placeholder_text',
          body_excerpt: bodySnapshot.slice(0, 500),
        });
      }

      await clickOptionForAnswer(h5Page, previewQuestion.answer || 'A', previewQuestion.type);
      await h5Page.getByRole('button', { name: '提交答案' }).click();
      await h5Page.locator('.analysis-card').waitFor({ state: 'visible', timeout: 10000 });

      const domQuestion = await extractDomQuestion(h5Page);
      const expected = candidateToComparable(candidateByNo.get(questionNo));
      const live = previewQuestionToComparable(consistencyByNo.get(questionNo));
      const domAnswerText = normText(domQuestion.answer.replace(/^正确答案：/, '').trim());
      const domAnswerMatch = domAnswerText.match(/^([A-DTF])/);
      const actual = {
        question_no: questionNo,
        stem: domQuestion.stem,
        options: {
          A: normText(domQuestion.options.A || ''),
          B: normText(domQuestion.options.B || ''),
          C: normText(domQuestion.options.C || ''),
          D: normText(domQuestion.options.D || ''),
        },
        material: domQuestion.material,
        answer: live.answer ? normText(domAnswerMatch?.[1] || '') : '',
        analysis: live.analysis ? domQuestion.analysis : '',
        answer_unknown_reason: live.answer ? '' : domAnswerText,
        analysis_unknown_reason: live.analysis ? '' : domQuestion.analysis,
        visual_summary: live.visual_summary,
        image_asset_ids: live.image_asset_ids,
      };
      const mismatches = [
        ...compareComparable(expected, live),
        ...compareComparable(live, actual),
      ];
      const overflowImages = array(domQuestion.image_stats).filter((item) => item.overflow);

      const questionPrefix = `q${String(questionNo).padStart(2, '0')}`;
      const h5Shot = path.join(h5Dir, `${questionPrefix}-h5-mobile.png`);
      await h5Page.screenshot({ path: h5Shot, fullPage: true });
      h5Audit.screenshots.push(h5Shot);
      await saveJson(path.join(h5Dir, `${questionPrefix}-live-api.json`), previewQuestion);
      await saveJson(path.join(h5Dir, `${questionPrefix}-compare-summary.json`), {
        question_no: questionNo,
        dom: domQuestion,
        expected,
        live,
        mismatches,
        overflow_images: overflowImages,
      });

      if (mismatches.length || overflowImages.length) {
        h5Audit.failed_questions.push({
          question_no: questionNo,
          mismatches,
          overflow_images: overflowImages,
          screenshot: h5Shot,
        });
      }

      if (index < consistencyPaper.questions.length - 1) {
        await h5Page.getByRole('button', { name: '下一题' }).click();
        await h5Page.waitForTimeout(300);
      }
    }

    const publishPreviewPaper = await getJsonWithRetry(
      apiCtx,
      h5Token,
      `/api/preview-papers/${publishPreviewMeta.paper_id}`,
    );
    const publishContext = await browser.newContext({
      ...devices['iPhone 13'],
      viewport: { width: 390, height: 844 },
    });
    await publishContext.addInitScript((token) => window.localStorage.setItem('h5_token', token), h5Token);
    const publishPage = await publishContext.newPage();
    await publishPage.goto(`${h5Base}${publishPreviewMeta.preview_route}`, {
      waitUntil: 'networkidle',
      timeout: 30000,
    });
    await publishPage.locator('.question-stem').waitFor({ state: 'visible', timeout: 15000 });
    const publishQuestion = array(publishPreviewPaper.questions)[0];
    await clickOptionForAnswer(publishPage, publishQuestion?.answer || 'A', publishQuestion?.type);
    await publishPage.getByRole('button', { name: '提交答案' }).click();
    await publishPage.locator('.analysis-card').waitFor({ state: 'visible', timeout: 10000 });
    const publishDom = await extractDomQuestion(publishPage);
    const publishShot = path.join(screenshotDir, 'publish-preview-h5.png');
    await publishPage.screenshot({ path: publishShot, fullPage: true });
    publishSmoke.screenshots.push(publishShot);
    publishSmoke.preview_meta = publishPreviewMeta;
    publishSmoke.preview_paper = publishPreviewPaper;
    publishSmoke.dom = publishDom;
    publishSmoke.checks.previewRouteReachable = true;
    publishSmoke.checks.answerVisible = Boolean(normText(publishDom.answer));
    publishSmoke.checks.analysisVisible = Boolean(normText(publishDom.analysis));
    publishSmoke.checks.productionSafe = publishPreviewPaper.production_published === false;
    await publishContext.close();

    for (const device of [
      { name: 'iPhone SE', ...devices['iPhone SE'] },
      {
        name: 'Android Pixel',
        userAgent:
          'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        viewport: { width: 412, height: 915 },
        deviceScaleFactor: 2.625,
        isMobile: true,
        hasTouch: true,
      },
    ]) {
      const smokeContext = await browser.newContext(device);
      await smokeContext.addInitScript((token) => window.localStorage.setItem('h5_token', token), h5Token);
      const smokePage = await smokeContext.newPage();
      await smokePage.goto(`${h5Base}${consistencyPreview.preview_route}`, {
        waitUntil: 'networkidle',
        timeout: 30000,
      });
      await smokePage.locator('.question-stem').waitFor({ state: 'visible', timeout: 15000 });
      const smokeBody = normText(await smokePage.locator('body').innerText());
      const smokeImages = await smokePage.evaluate(() => {
        const viewportWidth = window.innerWidth;
        return Array.from(document.querySelectorAll('img')).map((image) => {
          const rect = image.getBoundingClientRect();
          return { overflow: rect.width > viewportWidth + 1 };
        });
      });
      h5Audit.mobile_smoke.push({
        device: device.name,
        no_placeholder_text:
          !/\bundefined\b/i.test(smokeBody) &&
          !/\[object Object\]/.test(smokeBody) &&
          !/visual parse unavailable/i.test(smokeBody),
        image_overflow_count: smokeImages.filter((item) => item.overflow).length,
      });
      await smokeContext.close();
    }

    await saveJson(path.join(m6Dir, 'admin-review-playwright.json'), adminAudit);
    await saveJson(path.join(m6Dir, 'publish-smoke.json'), publishSmoke);
    await saveJson(path.join(h5Dir, 'playwright-h5-consistency.json'), h5Audit);
  } finally {
    await browser.close();
    await apiCtx.dispose();
  }
}

await main();
