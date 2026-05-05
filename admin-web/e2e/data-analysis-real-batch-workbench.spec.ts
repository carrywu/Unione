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
  createParseTask,
  startTrace,
  stopTrace,
  uploadPdfViaApi,
  waitForTaskDone,
  writeJson,
} from '../../e2e/commercial-ocr.helpers';


const REAL_FIXTURE_ROOT = process.env.E2E_REAL_BATCH_FIXTURE_ROOT || '';
const REAL_FIXTURE_NAME = process.env.E2E_REAL_BATCH_FIXTURE_NAME || '';

async function createBank(api: Awaited<ReturnType<typeof createAdminApiContext>>['auth'], name: string) {
  const response = await api.post('/admin/banks', {
    data: {
      name,
      subject: '资料分析',
      source: 'playwright-data-analysis-real-batch',
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
  const preview = await api.auth.post(`/admin/pdf/task/${taskId}/h5-consistency-preview`, {
    data: { reason: 'playwright-data-analysis-real-batch-workbench' },
  });
  expect(preview.ok()).toBeTruthy();
  const previewBody = await preview.json();
  return {
    paperId: String(previewBody.data.paper_id),
    preview: previewBody.data as Record<string, any>,
  };
}

test.describe('data analysis real batch workbench', () => {
  test.skip(!REAL_FIXTURE_ROOT || !REAL_FIXTURE_NAME, 'requires generated real batch fixture env');

  test('renders real batch smoke summary and keeps approve blocked for incomplete materials', async ({ page, context, browser }) => {
    const artifacts = await artifactPaths('admin', 'data-analysis-real-batch-workbench');
    const diagnostics = attachDiagnostics(page);
    await startTrace(context);
    const api = await createAdminApiContext();
    let previewRoute = '';

    try {
      await configureCommercialFixture(api.auth, REAL_FIXTURE_NAME, REAL_FIXTURE_ROOT);
      const bank = await createBank(api.auth, `资料分析真实批量-${Date.now()}`);
      const fileUrl = await uploadPdfViaApi(api.auth);
      const taskId = await createParseTask(api.auth, bank.id, fileUrl);
      await waitForTaskDone(api.auth, taskId);
      const previewMeta = await createPreviewRoute(api, taskId);
      previewRoute = `${H5_URL}${String(previewMeta.preview.preview_route || '')}`;

      await adminLogin(page);
      await page.goto(`${ADMIN_URL}/workbench?bankId=${bank.id}&taskId=${taskId}`);
      await expect(page.getByTestId('data-analysis-material-group')).toBeVisible();
      await expect(page.getByTestId('data-analysis-visual-context')).toContainText('material_complete');
      await expect(page.getByTestId('data-analysis-understanding')).toContainText('calculation_reasoning');
      await expect(page.getByTestId('data-analysis-quality-gate')).toContainText('需复核');
      await expect(page.getByTestId('data-analysis-quality-gate')).toContainText('llm_cannot_solve_question');
      await expect(page.getByText('bbox_source')).toBeVisible();
      await expect(page.getByText('tesseract_local_ocr')).toBeVisible();
      await expect(page.getByRole('button', { name: '审核通过' })).toBeDisabled();
      await assertNoUiGarbage(page);
      await capture(page, artifacts.screenshots, '01-admin-real-batch-workbench');

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
        await expect(h5Page.getByTestId('shared-material-card')).not.toHaveText('');
        await capture(h5Page, artifacts.screenshots, '02-h5-real-batch-preview');
        await assertNoUiGarbage(h5Page);
        await assertNoSevereBrowserErrors(h5Diagnostics);
      } finally {
        await h5Page.close();
      }

      await writeJson(path.join(artifacts.root, 'final-state.json'), {
        fixtureRoot: REAL_FIXTURE_ROOT,
        fixtureName: REAL_FIXTURE_NAME,
        previewRoute,
      });
    } finally {
      await writeJson(path.join(artifacts.root, 'console.json'), diagnostics);
      await stopTrace(context, path.join(artifacts.traces, 'data-analysis-real-batch-workbench.zip'));
      await api.dispose();
    }

    await assertNoSevereBrowserErrors(diagnostics);
  });
});
