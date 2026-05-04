import path from 'node:path';

import { expect, test } from 'playwright/test';

import {
  ADMIN_URL,
  SAMPLE_PDF_PATH,
  artifactPaths,
  assertNoSevereBrowserErrors,
  assertNoUiGarbage,
  attachDiagnostics,
  capture,
  configureCommercialFixture,
  createAdminApiContext,
  createDraftFromCandidates,
  fetchPaperCandidates,
  getFirstBankId,
  startTrace,
  stopTrace,
  waitForTaskDone,
  writeJson,
} from './commercial-ocr.helpers';

test.describe('commercial OCR admin full-chain', () => {
  test('blocked fixture stays gated out of draft/publish', async ({ page, context }) => {
    const artifacts = await artifactPaths('admin', 'blocked-review-gate');
    const diagnostics = attachDiagnostics(page);
    await startTrace(context);
    const api = await createAdminApiContext();
    let taskId = '';

    try {
      const bankId = await getFirstBankId(api.auth);
      await configureCommercialFixture(api.auth, 'shared_material_17_20_blocks.json');

      await page.goto(`${ADMIN_URL}/login`);
      await page.locator('.login-panel input').nth(0).fill('admin');
      await page.locator('.login-panel input').nth(1).fill('admin');
      await page.getByTestId('admin-login-submit').click();
      await page.waitForURL(/dashboard/);
      await capture(page, artifacts.screenshots, '01-admin-login');

      await page.goto(`${ADMIN_URL}/banks/${bankId}/upload`);
      await page.locator('input[type="file"]').setInputFiles(SAMPLE_PDF_PATH);
      const parseResponsePromise = page.waitForResponse((response) =>
        response.url().includes('/admin/pdf/parse') && response.request().method() === 'POST',
      );
      await page.getByTestId('start-upload-parse').click();
      const parseResponse = await parseResponsePromise;
      const parseBody = await parseResponse.json();
      taskId = parseBody.data.task_id as string;
      await capture(page, artifacts.screenshots, '02-upload-started');

      await expect(page.getByTestId('enter-review-edit')).toBeVisible({ timeout: 120_000 });
      await capture(page, artifacts.screenshots, '03-upload-finished');

      await page.goto(`${ADMIN_URL}/pdf/tasks/${taskId}/paper-review`);
      await expect(page.getByTestId('paper-review-overview')).toBeVisible();
      await page.locator('.candidate-row').filter({ hasText: '第 17 题' }).first().click();
      await expect(page.getByTestId('quality-gate-badge')).toContainText('review_ready=false');
      await expect(page.getByTestId('shared-material-panel')).toContainText('根据以下资料，回答17-20题');
      await expect(page.getByTestId('similarity-panel')).toContainText(/相似题|暂无相似题候选|命中 \d+ 个相似候选/);
      await expect(page.getByRole('button', { name: '加入试卷' })).toBeDisabled();
      await assertNoUiGarbage(page);
      await capture(page, artifacts.screenshots, '04-blocked-review');

      const candidates = await fetchPaperCandidates(api.auth, taskId);
      const draftAttempt = await createDraftFromCandidates(api.auth, candidates, 'blocked-playwright');
      expect(draftAttempt.status()).toBe(400);
      const draftBody = await draftAttempt.json();
      expect(String(draftBody.message || '')).toContain('不可入卷');
      expect(String(draftBody.message || '')).toContain('quality gate 未通过');

      const finalState = {
        taskId,
        candidateSummary: candidates.summary,
        questionNos: (candidates.questions || []).map((item: Record<string, unknown>) => item.question_no),
        blockedMessage: draftBody.message,
      };
      await writeJson(path.join(artifacts.root, 'final-admin-review-state.json'), finalState);
      await writeJson(path.join(artifacts.root, 'network.json'), {
        blockedDraftStatus: draftAttempt.status(),
      });
    } finally {
      await writeJson(path.join(artifacts.root, 'console.json'), diagnostics);
      await stopTrace(context, path.join(artifacts.traces, 'blocked-review-gate.zip'));
      await api.dispose();
    }

    await assertNoSevereBrowserErrors(diagnostics);
  });

  test('complete fixture can be reviewed and preview-published', async ({ page, context }) => {
    const artifacts = await artifactPaths('admin', 'complete-preview-publish');
    const diagnostics = attachDiagnostics(page);
    await startTrace(context);
    const api = await createAdminApiContext();
    let taskId = '';
    let previewRoute = '';

    try {
      const bankId = await getFirstBankId(api.auth);
      await configureCommercialFixture(api.auth, 'shared_material_17_20_complete_blocks.json');

      await page.goto(`${ADMIN_URL}/login`);
      await page.locator('.login-panel input').nth(0).fill('admin');
      await page.locator('.login-panel input').nth(1).fill('admin');
      await page.getByTestId('admin-login-submit').click();
      await page.waitForURL(/dashboard/);
      await capture(page, artifacts.screenshots, '01-admin-login');

      await page.goto(`${ADMIN_URL}/banks/${bankId}/upload`);
      await page.locator('input[type="file"]').setInputFiles(SAMPLE_PDF_PATH);
      const parseResponsePromise = page.waitForResponse((response) =>
        response.url().includes('/admin/pdf/parse') && response.request().method() === 'POST',
      );
      await page.getByTestId('start-upload-parse').click();
      const parseResponse = await parseResponsePromise;
      const parseBody = await parseResponse.json();
      taskId = parseBody.data.task_id as string;
      await capture(page, artifacts.screenshots, '02-upload-started');

      await expect(page.getByTestId('enter-review-edit')).toBeVisible({ timeout: 120_000 });
      await capture(page, artifacts.screenshots, '03-upload-finished');

      await page.goto(`${ADMIN_URL}/pdf/tasks/${taskId}/paper-review`);
      await expect(page.getByTestId('paper-review-overview')).toBeVisible();
      await expect(page.getByTestId('paper-review-overview')).toContainText('mock_commercial_ocr');

      const sharedStem = '根据以下资料，回答17-20题';
      for (const questionNo of [17, 18, 19, 20]) {
        await page.locator('.candidate-row').filter({ hasText: `第 ${questionNo} 题` }).first().click();
        await expect(page.getByTestId('shared-material-panel')).toContainText(sharedStem);
        await expect(page.getByTestId('shared-material-panel').locator('img')).toHaveCount(2);
        const questionStem = await page.getByTestId('selected-question-stem').innerText();
        expect(questionStem).not.toContain(sharedStem);
        await expect(page.getByRole('button', { name: '加入试卷' })).toBeEnabled();
        await page.getByRole('button', { name: '加入试卷' }).click();
      }

      await expect(page.getByTestId('draft-paper').locator('.draft-question')).toHaveCount(4);
      await capture(page, artifacts.screenshots, '04-draft-ready');

      await page.getByRole('button', { name: '保存草稿' }).click();
      await expect(page.getByText('试卷草稿已保存')).toBeVisible();
      await page.getByRole('button', { name: 'Preview 发布' }).click();
      await expect(page.getByTestId('preview-publish-panel')).toBeVisible();
      previewRoute = (await page.getByTestId('preview-publish-panel').innerText()).match(/\/quiz-preview\/[A-Za-z0-9-]+/)?.[0] || '';
      expect(previewRoute).toContain('/quiz-preview/');
      await assertNoUiGarbage(page);
      await capture(page, artifacts.screenshots, '05-preview-published');

      const candidates = await fetchPaperCandidates(api.auth, taskId);
      const finalState = {
        taskId,
        previewRoute,
        candidateSummary: candidates.summary,
        questionNos: (candidates.questions || []).map((item: Record<string, unknown>) => item.question_no),
        providerTraceRefs: Array.from(
          new Set((candidates.questions || []).map((item: Record<string, unknown>) => item.provider_trace_ref)),
        ),
      };
      await writeJson(path.join(artifacts.root, 'final-admin-review-state.json'), finalState);
      await writeJson(path.join(artifacts.root, 'network.json'), {
        paperReviewUrl: `${ADMIN_URL}/pdf/tasks/${taskId}/paper-review`,
        previewRoute,
      });
    } finally {
      await writeJson(path.join(artifacts.root, 'console.json'), diagnostics);
      await stopTrace(context, path.join(artifacts.traces, 'complete-preview-publish.zip'));
      await api.dispose();
    }

    await assertNoSevereBrowserErrors(diagnostics);
  });
});
