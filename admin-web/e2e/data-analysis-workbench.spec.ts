import path from 'node:path';

import { expect, test } from 'playwright/test';

import {
  ADMIN_URL,
  H5_URL,
  artifactPaths,
  assertNoSevereBrowserErrors,
  assertNoUiGarbage,
  attachDiagnostics,
  capture,
  configureCommercialFixture,
  createAdminApiContext,
  createDraftFromCandidates,
  createParseTask,
  fetchPaperCandidates,
  startTrace,
  stopTrace,
  uploadPdfViaApi,
  waitForTaskDone,
  writeJson,
} from '../../e2e/commercial-ocr.helpers';

async function createBank(api: Awaited<ReturnType<typeof createAdminApiContext>>['auth'], name: string) {
  const response = await api.post('/admin/banks', {
    data: {
      name,
      subject: '资料分析',
      source: 'playwright-data-analysis',
      year: 2026,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  return body.data as { id: string; name: string };
}

async function adminLogin(page: Parameters<typeof attachDiagnostics>[0]) {
  await page.goto(`${ADMIN_URL}/login`);
  await page.locator('.login-panel input').nth(0).fill('admin');
  await page.locator('.login-panel input').nth(1).fill('admin');
  await page.getByTestId('admin-login-submit').click();
  await page.waitForURL(/dashboard/);
}

async function h5Login(page: Parameters<typeof attachDiagnostics>[0]) {
  await page.goto(`${H5_URL}/login`);
  await page.getByTestId('fill-demo-account').click();
  await page.getByTestId('login-submit').click();
  await page.waitForURL(`${H5_URL}/`);
}

async function createPreviewRoute(
  api: Awaited<ReturnType<typeof createAdminApiContext>>,
  taskId: string,
) {
  const candidates = await fetchPaperCandidates(api.auth, taskId);
  const draft = await createDraftFromCandidates(api.auth, candidates, `playwright-workbench-${Date.now()}`);
  expect(draft.ok()).toBeTruthy();
  const draftBody = await draft.json();
  const paperId = draftBody.data.paper_id as string;
  const publish = await api.auth.post(`/admin/pdf/papers/${paperId}/publish-preview`, {
    data: { dry_run: true, reason: 'playwright-data-analysis-workbench' },
  });
  expect(publish.ok()).toBeTruthy();
  const publishBody = await publish.json();
  return {
    paperId,
    preview: publishBody.data as Record<string, any>,
    candidates,
  };
}

test.describe('data analysis workbench', () => {
  test('routes banks to workbench and preserves shared material through admin and h5 preview', async ({ page, context, browser }) => {
    const artifacts = await artifactPaths('admin', 'data-analysis-workbench');
    const diagnostics = attachDiagnostics(page);
    await startTrace(context);
    const api = await createAdminApiContext();
    let bank: { id: string; name: string } | null = null;
    let taskId = '';
    let previewRoute = '';

    try {
      await configureCommercialFixture(api.auth, 'shared_material_17_20_complete_blocks.json');
      bank = await createBank(api.auth, `资料分析工作台-${Date.now()}`);
      const fileUrl = await uploadPdfViaApi(api.auth);
      taskId = await createParseTask(api.auth, bank.id, fileUrl);
      await waitForTaskDone(api.auth, taskId);

      const previewMeta = await createPreviewRoute(api, taskId);
      previewRoute = `${H5_URL}${String(previewMeta.preview.preview_route || '')}`;

      await adminLogin(page);
      await capture(page, artifacts.screenshots, '01-admin-login');

      await page.goto(`${ADMIN_URL}/banks`);
      await page.getByPlaceholder('搜索题库名称').fill(bank.name);
      await page.getByPlaceholder('搜索题库名称').press('Enter');
      await expect(page.getByRole('button', { name: bank.name })).toBeVisible();
      await page.getByRole('button', { name: bank.name }).click();
      await expect(page).toHaveURL(new RegExp(`/workbench\\?bankId=${bank.id}$`));
      await expect(page.getByTestId('data-analysis-material-group')).toBeVisible();
      await capture(page, artifacts.screenshots, '02-entered-workbench');

      await page.goto(`${ADMIN_URL}/banks/${bank.id}/questions?taskId=${taskId}`);
      await expect(page).toHaveURL(new RegExp(`/workbench\\?bankId=${bank.id}&taskId=${taskId}`));
      await expect(page.getByTestId('data-analysis-material-group')).toContainText('17 - 18 - 19 - 20');
      await expect(page.getByTestId('data-analysis-visual-context')).toContainText('chart_title_present');
      await expect(page.getByTestId('data-analysis-visual-context')).toContainText('table_header_present');
      await expect(page.getByTestId('data-analysis-visual-context')).toContainText('unit_present');
      await expect(page.getByTestId('data-analysis-understanding')).toContainText('calculation_reasoning');
      await expect(page.getByTestId('calculation-reasoning')).not.toContainText('未提供');
      await expect(page.getByText('17-20共享材料')).toBeVisible();
      await expect(page.getByText('17题')).toBeVisible();
      await expect(page.getByRole('button', { name: '待审核' })).toBeVisible();
      await expect(page.getByRole('button', { name: '审核通过' })).toBeVisible();
      await expect(page.getByRole('button', { name: '需复核' })).toBeVisible();
      await expect(page.getByRole('button', { name: '打开 H5 预览' })).toBeVisible();
      await expect(page.getByRole('button', { name: '发布到题库' })).toBeVisible();
      await expect(page.getByText('保留草稿')).toHaveCount(0);

      for (const questionNo of [17, 18, 19, 20]) {
        await page.locator('.queue-question').filter({ hasText: new RegExp(`^${questionNo}\\.`) }).first().click();
        await expect(page.getByTestId('data-analysis-material-group')).toContainText('根据以下资料，回答17-20题');
        await expect(page.locator('.queue-question.active .queue-question-main strong')).toHaveText(`${questionNo}.`);
        await expect(page.locator('.phone-status strong')).toContainText(`${questionNo} /`);
      }

      await assertNoUiGarbage(page);
      await capture(page, artifacts.screenshots, '03-workbench-shared-material');

      const h5Page = await browser.newPage({
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      });
      const h5Diagnostics = attachDiagnostics(h5Page);
      try {
        await h5Login(h5Page);
        await h5Page.goto(previewRoute);
        await expect(h5Page.getByTestId('shared-material-card')).toBeVisible();
        await expect(h5Page.getByTestId('shared-material-card')).toContainText('根据以下资料，回答17-20题');
        await expect(h5Page.getByTestId('question-stem')).toContainText('17');
        await capture(h5Page, artifacts.screenshots, '04-h5-preview-opened');
        await h5Page.getByTestId('option-B').click();
        await h5Page.getByTestId('submit-answer-button').click();
        await expect(h5Page.getByTestId('analysis-card')).toBeVisible();
        await h5Page.getByTestId('next-question-button').click();
        await expect(h5Page.getByTestId('shared-material-card')).toContainText('根据以下资料，回答17-20题');
        await expect(h5Page.getByTestId('question-stem')).toContainText('18');
        await capture(h5Page, artifacts.screenshots, '05-h5-preview-next-question');
        await assertNoUiGarbage(h5Page);
        await assertNoSevereBrowserErrors(h5Diagnostics);
      } finally {
        await h5Page.close();
      }

      await writeJson(path.join(artifacts.root, 'final-state.json'), {
        bankId: bank.id,
        taskId,
        previewRoute,
      });
    } finally {
      await writeJson(path.join(artifacts.root, 'console.json'), diagnostics);
      await stopTrace(context, path.join(artifacts.traces, 'data-analysis-workbench.zip'));
      await api.dispose();
    }

    await assertNoSevereBrowserErrors(diagnostics);
  });

  test('answer conflict fixture is marked for human review in workbench', async ({ page, context }) => {
    const artifacts = await artifactPaths('admin', 'data-analysis-workbench-conflict');
    const diagnostics = attachDiagnostics(page);
    await startTrace(context);
    const api = await createAdminApiContext();

    try {
      await configureCommercialFixture(api.auth, 'shared_material_17_20_soft_warning_blocks.json');
      const bank = await createBank(api.auth, `资料分析冲突-${Date.now()}`);
      const fileUrl = await uploadPdfViaApi(api.auth);
      const taskId = await createParseTask(api.auth, bank.id, fileUrl);
      await waitForTaskDone(api.auth, taskId);

      await adminLogin(page);
      await page.goto(`${ADMIN_URL}/workbench?bankId=${bank.id}`);
      await expect(page.getByTestId('data-analysis-understanding')).toContainText('ocr_answer_agreement');
      await expect(page.locator('.queue-question.active .queue-tag.danger')).toHaveText('答案冲突');
      await expect(page.getByTestId('data-analysis-quality-gate')).toContainText('需复核');
      await assertNoUiGarbage(page);
      await capture(page, artifacts.screenshots, '01-conflict-workbench');
    } finally {
      await writeJson(path.join(artifacts.root, 'console.json'), diagnostics);
      await stopTrace(context, path.join(artifacts.traces, 'data-analysis-workbench-conflict.zip'));
      await api.dispose();
    }

    await assertNoSevereBrowserErrors(diagnostics);
  });
});
