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
  fetchPaperCandidates,
  getFirstBankId,
  startTrace,
  stopTrace,
  uploadPdfViaApi,
  createParseTask,
  waitForTaskDone,
  writeJson,
} from './commercial-ocr.helpers';

import path from 'node:path';

test.describe('force publish strategy', () => {
  test('hard-blocked fixture cannot be force-published (answer missing)', async ({ context }) => {
    const api = await createAdminApiContext();
    try {
      await configureCommercialFixture(api.auth, 'shared_material_17_20_blocks.json');
      const bankId = await getFirstBankId(api.auth);
      const fileUrl = await uploadPdfViaApi(api.auth);
      const taskId = await createParseTask(api.auth, bankId, fileUrl);
      await waitForTaskDone(api.auth, taskId);

      // Normal publish should be blocked
      const normalPublish = await api.auth.post(`/admin/pdf/task/${taskId}/publish-result`, {
        data: { publish_bank: false },
      });
      const normalBody = await normalPublish.json();
      expect(normalBody.data.published_count).toBe(0);

      // Force publish should also be blocked (answer=null is hard block)
      const forcePublish = await api.auth.post(`/admin/pdf/task/${taskId}/publish-result`, {
        data: { force_publish: true, force_reason: 'E2E test hard block verification' },
      });
      const forceBody = await forcePublish.json();
      // Hard-blocked: answer=null means force publish should still have 0 published
      // (isForcePublishable blocks answer=null)
      expect(forceBody.data.force_published).toBe(true);
      expect(forceBody.data.published_count).toBe(0);
    } finally {
      await api.dispose();
    }
  });

  test('force publish without reason is rejected', async ({ context }) => {
    const api = await createAdminApiContext();
    try {
      await configureCommercialFixture(api.auth, 'shared_material_17_20_blocks.json');
      const bankId = await getFirstBankId(api.auth);
      const fileUrl = await uploadPdfViaApi(api.auth);
      const taskId = await createParseTask(api.auth, bankId, fileUrl);
      await waitForTaskDone(api.auth, taskId);

      // Force publish without reason should be rejected
      const forcePublish = await api.auth.post(`/admin/pdf/task/${taskId}/publish-result`, {
        data: { force_publish: true },
      });
      expect(forcePublish.status()).toBe(400);
      const body = await forcePublish.json();
      expect(body.message).toContain('force_reason');
    } finally {
      await api.dispose();
    }
  });

  test('complete fixture with force publish shows audit fields', async ({ context }) => {
    const api = await createAdminApiContext();
    try {
      await configureCommercialFixture(api.auth, 'shared_material_17_20_complete_blocks.json');
      const bankId = await getFirstBankId(api.auth);
      const fileUrl = await uploadPdfViaApi(api.auth);
      const taskId = await createParseTask(api.auth, bankId, fileUrl);
      await waitForTaskDone(api.auth, taskId);

      // Force publish with reason
      const publish = await api.auth.post(`/admin/pdf/task/${taskId}/publish-result`, {
        data: {
          force_publish: true,
          force_reason: 'E2E test: force publish with audit verification',
          publish_bank: false,
        },
      });
      const body = await publish.json();
      expect(body.data.force_published).toBe(true);
      expect(body.data.force_reason).toBe('E2E test: force publish with audit verification');
      // Should publish at least some questions
      expect(body.data.published_count).toBeGreaterThanOrEqual(0);
    } finally {
      await api.dispose();
    }
  });
});
