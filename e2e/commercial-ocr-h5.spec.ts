import path from 'node:path';

import { expect, test } from 'playwright/test';

import {
  H5_URL,
  artifactPaths,
  assertNoSevereBrowserErrors,
  assertNoUiGarbage,
  attachDiagnostics,
  capture,
  createPreviewPaperFromFixture,
  startTrace,
  stopTrace,
  writeJson,
} from './commercial-ocr.helpers';

test.use({
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
});

test('h5 preview paper preserves shared material across 17-20', async ({ page, context }) => {
  const artifacts = await artifactPaths('h5', 'preview-paper-mobile');
  const diagnostics = attachDiagnostics(page);
  await startTrace(context);

  const preview = await createPreviewPaperFromFixture(
    'shared_material_17_20_complete_blocks.json',
    'playwright-h5-preview',
  );
  const previewRoute = `${H5_URL}${preview.preview.preview_route}`;

  try {
    await page.goto(`${H5_URL}/login`);
    await page.getByTestId('fill-demo-account').click();
    await page.getByTestId('login-submit').click();
    await page.waitForURL(`${H5_URL}/`);
    await capture(page, artifacts.screenshots, '01-h5-login');

    await page.goto(previewRoute);
    await expect(page.getByTestId('shared-material-card')).toBeVisible();
    await expect(page.getByTestId('question-card')).toBeVisible();
    await capture(page, artifacts.screenshots, '02-preview-opened');

    const sharedStem = await page.getByTestId('shared-material-card').innerText();
    expect(sharedStem).toContain('根据以下资料，回答17-20题');
    await expect(page.getByTestId('shared-material-card').locator('img')).toHaveCount(2);

    const answers: Array<[number, string]> = [
      [17, 'B'],
      [18, 'A'],
      [19, 'D'],
      [20, 'B'],
    ];

    for (const [questionNo, answer] of answers) {
      await expect(page.getByTestId('question-stem')).toContainText(String(questionNo));
      await expect(page.getByTestId('shared-material-card')).toContainText('根据以下资料，回答17-20题');
      const stemText = await page.getByTestId('question-stem').innerText();
      expect(stemText).not.toContain('根据以下资料，回答17-20题');

      await page.getByTestId(`option-${answer}`).click();
      await page.getByTestId('submit-answer-button').click();
      await expect(page.getByTestId('analysis-card')).toBeVisible();
      await capture(page, artifacts.screenshots, `question-${questionNo}-analysis`);

      const noHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2);
      expect(noHorizontalOverflow).toBeTruthy();
      await assertNoUiGarbage(page);

      if (questionNo !== 20) {
        await page.getByTestId('next-question-button').click();
      }
    }

    await page.getByTestId('next-question-button').click();
    await page.waitForURL(/\/result$/);
    await capture(page, artifacts.screenshots, '03-result-page');

    await writeJson(path.join(artifacts.root, 'final-h5-state.json'), {
      paperId: preview.paperId,
      taskId: preview.taskId,
      previewRoute,
      answeredQuestions: answers.map(([questionNo, answer]) => ({ questionNo, answer })),
    });
    await writeJson(path.join(artifacts.root, 'network.json'), {
      previewApiPath: preview.preview.preview_api_path,
      previewRoute: preview.preview.preview_route,
    });
  } finally {
    await writeJson(path.join(artifacts.root, 'console.json'), diagnostics);
    await stopTrace(context, path.join(artifacts.traces, 'preview-paper-mobile.zip'));
  }

  await assertNoSevereBrowserErrors(diagnostics);
});
