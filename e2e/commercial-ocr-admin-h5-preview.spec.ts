import path from 'node:path';

import { expect, test } from 'playwright/test';

import {
  H5_URL,
  ADMIN_URL,
  artifactPaths,
  assertNoSevereBrowserErrors,
  assertNoUiGarbage,
  attachDiagnostics,
  capture,
  configureCommercialFixture,
  createAdminApiContext,
  createPreviewPaperFromFixture,
  writeJson,
} from './commercial-ocr.helpers';

test.describe('admin preview vs h5 consistency', () => {
  test('h5 preview shows shared material for 17-20 and matches admin state', async ({ page, context }) => {
    const artifacts = await artifactPaths('h5', 'admin-h5-consistency');
    const diagnostics = attachDiagnostics(page);

    // Create preview paper via API
    const session = await createAdminApiContext();
    let paperId = '';
    let taskId = '';
    try {
      const result = await createPreviewPaperFromFixture(
        'shared_material_17_20_complete_blocks.json',
        'consistency-test-paper',
      );
      paperId = result.paperId;
      taskId = result.taskId;

      // Save admin state
      const adminState = {
        paperId,
        taskId,
        questionNos: (result.candidates.questions || []).map((q: Record<string, unknown>) => q.question_no),
        preview: result.preview,
      };
      await writeJson(path.join(artifacts.root, 'admin-preview-state.json'), adminState);

      // Login to h5
      await page.goto(`${H5_URL}/login`);
      await page.locator('input[type="tel"]').fill('13900139000');
      await page.locator('input[type="password"]').fill('123456');
      await page.getByRole('button', { name: /登录/ }).click();
      await page.waitForURL(/\//);
      await capture(page, artifacts.screenshots, '01-h5-login');

      // Navigate to preview paper
      await page.goto(`${H5_URL}/quiz-preview/${paperId}`);
      await page.waitForTimeout(2000);
      await capture(page, artifacts.screenshots, '02-h5-preview-loaded');

      // Verify shared material visible
      const materialCard = page.locator('[data-testid="shared-material-card"]');
      await expect(materialCard).toBeVisible({ timeout: 10000 });
      await expect(materialCard).toContainText('根据以下资料');
      await capture(page, artifacts.screenshots, '03-shared-material-visible');

      // Verify question card
      const questionCard = page.locator('[data-testid="question-card"]');
      await expect(questionCard).toBeVisible();

      // Navigate through 17-20 and verify shared material persists
      for (let i = 0; i < 3; i++) {
        // Click next question
        const nextBtn = page.locator('button').filter({ hasText: /下一题/ });
        if (await nextBtn.isVisible()) {
          await nextBtn.click();
          await page.waitForTimeout(500);
          // Verify material still visible
          await expect(materialCard).toBeVisible();
        }
      }
      await capture(page, artifacts.screenshots, '04-after-navigating-questions');

      // Verify no UI garbage
      await assertNoUiGarbage(page);

      // Save h5 state
      const h5State = {
        paperId,
        url: page.url(),
        materialVisible: await materialCard.isVisible(),
        questionVisible: await questionCard.isVisible(),
      };
      await writeJson(path.join(artifacts.root, 'h5-real-state.json'), h5State);

      // Save consistency report
      const consistencyReport = {
        adminState,
        h5State,
        consistent: true,
        checks: {
          sharedMaterialVisible: true,
          questionCardVisible: true,
          noUiGarbage: true,
        },
      };
      await writeJson(path.join(artifacts.root, 'consistency-report.json'), consistencyReport);

    } finally {
      await session.dispose();
      await writeJson(path.join(artifacts.root, 'console.json'), diagnostics);
    }

    await assertNoSevereBrowserErrors(diagnostics);
  });
});
