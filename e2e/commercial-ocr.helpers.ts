import { promises as fs } from 'node:fs';
import path from 'node:path';

import { expect, request as playwrightRequest, type APIRequestContext, type BrowserContext, type Page } from 'playwright/test';

export const BACKEND_URL = process.env.E2E_BACKEND_URL || 'http://127.0.0.1:3010';
export const PDF_SERVICE_URL = process.env.E2E_PDF_SERVICE_URL || 'http://127.0.0.1:8001';
export const ADMIN_URL = process.env.E2E_ADMIN_URL || 'http://127.0.0.1:5174';
export const H5_URL = process.env.E2E_H5_URL || 'http://127.0.0.1:5173';
export const SAMPLE_PDF_PATH = path.resolve(process.cwd(), 'backend', 'sample-题本篇-3-7.pdf');
export const DEFAULT_COMMERCIAL_FIXTURE_ROOT = path.resolve(
  process.cwd(),
  'pdf-service',
  'tests',
  'fixtures',
  'commercial_ocr',
);
export const E2E_ARTIFACT_ROOT =
  process.env.E2E_ARTIFACT_DIR ||
  path.resolve(
    process.cwd(),
    'debug',
    'e2e-commercial-ocr',
    new Date().toISOString().replace(/[:.]/g, '-'),
  );

export type PageDiagnostics = {
  console: Array<{ type: string; text: string; location: string | null }>;
  pageErrors: string[];
  requestFailures: Array<{ url: string; method: string; failureText: string | null }>;
};

const ownedTraceContexts = new WeakSet<BrowserContext>();

export async function ensureDir(dir: string) {
  await fs.mkdir(dir, { recursive: true });
}

export async function artifactPaths(channel: 'admin' | 'h5', scenario: string) {
  const root = path.join(E2E_ARTIFACT_ROOT, channel, scenario);
  const screenshots = path.join(root, 'screenshots');
  const traces = path.join(root, 'traces');
  await Promise.all([ensureDir(root), ensureDir(screenshots), ensureDir(traces)]);
  return { root, screenshots, traces };
}

export function attachDiagnostics(page: Page): PageDiagnostics {
  const diagnostics: PageDiagnostics = {
    console: [],
    pageErrors: [],
    requestFailures: [],
  };
  page.on('console', (message) => {
    diagnostics.console.push({
      type: message.type(),
      text: message.text(),
      location: message.location()?.url || null,
    });
  });
  page.on('pageerror', (error) => {
    diagnostics.pageErrors.push(String(error));
  });
  page.on('requestfailed', (request) => {
    const url = request.url();
    if (url.endsWith('/favicon.ico')) return;
    diagnostics.requestFailures.push({
      url,
      method: request.method(),
      failureText: request.failure()?.errorText || null,
    });
  });
  return diagnostics;
}

export async function startTrace(context: BrowserContext) {
  try {
    await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
    ownedTraceContexts.add(context);
  } catch (error) {
    const message = String(error);
    if (!message.includes('Tracing has been already started')) {
      throw error;
    }
  }
}

export async function stopTrace(context: BrowserContext, tracePath: string) {
  if (!ownedTraceContexts.has(context)) {
    return;
  }
  try {
    await context.tracing.stop({ path: tracePath });
    ownedTraceContexts.delete(context);
  } catch (error) {
    const message = String(error);
    if (!message.includes('Must start tracing before stopping')) {
      throw error;
    }
  }
}

export async function writeJson(target: string, payload: unknown) {
  await fs.writeFile(target, JSON.stringify(payload, null, 2), 'utf-8');
}

export async function capture(page: Page, screenshotsDir: string, name: string) {
  const file = path.join(screenshotsDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

export async function assertNoUiGarbage(page: Page) {
  const bodyText = await page.locator('body').innerText();
  expect(bodyText).not.toContain('undefined');
  expect(bodyText).not.toContain('[object Object]');
  expect(bodyText).not.toContain('visual parse unavailable');
  expect(bodyText).not.toMatch(/\bnull\b/);
}

export async function assertNoSevereBrowserErrors(diagnostics: PageDiagnostics) {
  const consoleErrors = diagnostics.console.filter((entry) => entry.type === 'error');
  expect(consoleErrors, 'console errors').toEqual([]);
  expect(diagnostics.pageErrors, 'page errors').toEqual([]);
  // Allow aborted requests during navigation (common in SPA transitions)
  const realFailures = diagnostics.requestFailures.filter(
    (f) => !f.failureText?.includes('ERR_ABORTED'),
  );
  expect(realFailures, 'request failures (excluding navigation aborts)').toEqual([]);
}

export async function createAdminApiContext() {
  const anon = await playwrightRequest.newContext({
    baseURL: BACKEND_URL,
    ignoreHTTPSErrors: true,
  });
  const login = await anon.post('/api/auth/login', {
    data: { phone: 'admin', password: 'admin' },
  });
  expect(login.ok()).toBeTruthy();
  const loginBody = await login.json();
  const token = loginBody.data.access_token as string;
  const auth = await playwrightRequest.newContext({
    baseURL: BACKEND_URL,
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {
      Authorization: `Bearer ${token}`,
    },
  });
  return {
    anon,
    auth,
    token,
    async dispose() {
      await Promise.all([anon.dispose(), auth.dispose()]);
    },
  };
}

export async function configureCommercialFixture(
  api: APIRequestContext,
  fixtureName: string,
  fixtureRoot = DEFAULT_COMMERCIAL_FIXTURE_ROOT,
) {
  const response = await api.put('/admin/pdf-service/config', {
    data: {
      commercial_ocr_enabled: true,
      commercial_ocr_real_smoke: false,
      pdf_parse_primary_provider: 'mock_commercial_ocr',
      pdf_parse_fallback_providers: 'local_parser,mock_commercial_ocr',
      ocr_provider_trace_enabled: true,
      commercial_ocr_fixture_root: fixtureRoot,
      mock_commercial_ocr_fixture_name: fixtureName,
    },
  });
  expect(response.ok()).toBeTruthy();
}

export async function getFirstBankId(api: APIRequestContext) {
  const response = await api.get('/admin/banks');
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  const bankId = body.data?.list?.[0]?.id as string | undefined;
  expect(bankId).toBeTruthy();
  return bankId!;
}

export async function fetchPaperCandidates(api: APIRequestContext, taskId: string) {
  const response = await api.get(`/admin/pdf/task/${taskId}/paper-candidates`);
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  return body.data as Record<string, any>;
}

export async function createDraftFromCandidates(
  api: APIRequestContext,
  candidates: Record<string, any>,
  title: string,
) {
  const response = await api.post('/admin/pdf/papers/draft', {
    data: {
      title,
      source_task_id: candidates.taskId,
      source_bank_id: candidates.bankId,
      sections: [{ id: 'section-1', title: '自动候选题', order: 1 }],
      questions: candidates.questions,
    },
  });
  return response;
}

export async function uploadPdfViaApi(api: APIRequestContext) {
  const buffer = await fs.readFile(SAMPLE_PDF_PATH);
  const response = await api.post('/admin/upload/file', {
    multipart: {
      file: {
        name: path.basename(SAMPLE_PDF_PATH),
        mimeType: 'application/pdf',
        buffer,
      },
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  return body.data.url as string;
}

export async function createParseTask(api: APIRequestContext, bankId: string, fileUrl: string) {
  const response = await api.post('/admin/pdf/parse', {
    data: { bank_id: bankId, file_url: fileUrl },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  return body.data.task_id as string;
}

export async function waitForTaskDone(api: APIRequestContext, taskId: string, timeoutMs = 120_000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const response = await api.get(`/admin/pdf/task/${taskId}`);
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    const task = body.data as Record<string, any>;
    if (['done', 'failed', 'paused', 'cancelled', 'completed'].includes(String(task.status))) {
      return task;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error(`Timed out waiting for parse task ${taskId}`);
}

export async function createPreviewPaperFromFixture(fixtureName: string, title: string) {
  const session = await createAdminApiContext();
  try {
    await configureCommercialFixture(session.auth, fixtureName);
    const bankId = await getFirstBankId(session.auth);
    const fileUrl = await uploadPdfViaApi(session.auth);
    const taskId = await createParseTask(session.auth, bankId, fileUrl);
    await waitForTaskDone(session.auth, taskId);
    const candidates = await fetchPaperCandidates(session.auth, taskId);
    const draft = await createDraftFromCandidates(session.auth, candidates, title);
    expect(draft.ok()).toBeTruthy();
    const draftBody = await draft.json();
    const paperId = draftBody.data.paper_id as string;
    const publish = await session.auth.post(`/admin/pdf/papers/${paperId}/publish-preview`, {
      data: { dry_run: true, reason: `playwright-preview:${fixtureName}` },
    });
    expect(publish.ok()).toBeTruthy();
    const publishBody = await publish.json();
    return {
      bankId,
      taskId,
      paperId,
      candidates,
      preview: publishBody.data as Record<string, any>,
    };
  } finally {
    await session.dispose();
  }
}

export async function deleteTaskIfPossible(api: APIRequestContext, taskId: string) {
  if (!taskId) return;
  await api.delete(`/admin/pdf/task/${taskId}`).catch(() => undefined);
}
