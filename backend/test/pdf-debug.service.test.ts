import * as assert from 'node:assert/strict';
import axios from 'axios';
import { BadRequestException } from '@nestjs/common';
import { PdfService } from '../src/modules/pdf/pdf.service';

const task = {
  id: 'task-1',
  file_url: 'https://example.test/book.pdf',
  result_summary: JSON.stringify({ stats: { total: 1 } }),
};

const metadata = {
  run_id: 'task_task-1_pages_9_14',
  pages: '9-14',
  files: {
    summary: 'summary.json',
    review_manifest_json: 'review_manifest.json',
    review_manifest_csv: 'review_manifest.csv',
  },
  dirs: {
    overlays: 'debug/overlays',
    crops: 'debug/crops',
    page_screenshots: 'page_screenshots',
  },
  summary_preview: { page_limit: 5 },
};

function service(update = async () => undefined) {
  return new PdfService(
    {
      findOne: async () => task,
      update,
    } as any,
    {} as any,
    {} as any,
    {} as any,
    {} as any,
    {
      get: (key: string, fallback?: string) =>
        key === 'PDF_SERVICE_INTERNAL_TOKEN' ? 'token' : fallback,
    } as any,
    {} as any,
  );
}

async function run() {
  await testGenerateWritesDebugArtifacts();
  await testSummaryReviewAndArtifactProxy();
  await testIllegalPathRejected();
}

async function testGenerateWritesDebugArtifacts() {
  const updates: any[] = [];
  const originalPost = axios.post;
  (axios as any).post = async () => ({ data: metadata });
  try {
    const result = await service(async (id: string, patch: any) => {
      updates.push([id, patch]);
    }).generateDebugArtifacts('task-1', { pages: '9-14', clean_output: true });

    assert.deepEqual(result, metadata);
    assert.equal(updates[0][0], 'task-1');
    assert.deepEqual(JSON.parse(updates[0][1].result_summary), {
      stats: { total: 1 },
      debug_artifacts: metadata,
    });
  } finally {
    (axios as any).post = originalPost;
  }
}

async function testSummaryReviewAndArtifactProxy() {
  const originalGet = axios.get;
  const calls: string[] = [];
  (axios as any).get = async (_url: string, options: any) => {
    calls.push(options.params.path);
    if (options.params.path === 'summary.json') {
      return { data: { total_questions: 2 }, headers: { 'content-type': 'application/json' } };
    }
    if (options.params.path === 'review_manifest.json') {
      return { data: [{ question_id: 'q1' }], headers: { 'content-type': 'application/json' } };
    }
    return { data: Buffer.from('png'), headers: { 'content-type': 'image/png' } };
  };
  try {
    const svc = service();
    (svc as any).getDebugArtifacts = async () => metadata;

    assert.deepEqual(await svc.getDebugSummary('task-1'), { total_questions: 2 });
    assert.deepEqual((await svc.getDebugReviewManifest('task-1', 'json')).data, [
      { question_id: 'q1' },
    ]);
    assert.equal(
      (await svc.getDebugArtifact('task-1', 'debug/overlays/page_001_overlay.png')).contentType,
      'image/png',
    );
    assert.deepEqual(calls, [
      'summary.json',
      'review_manifest.json',
      'debug/overlays/page_001_overlay.png',
    ]);
  } finally {
    (axios as any).get = originalGet;
  }
}

async function testIllegalPathRejected() {
  const svc = service();
  (svc as any).getDebugArtifacts = async () => metadata;
  await assert.rejects(
    () => svc.getDebugArtifact('task-1', '../../etc/passwd'),
    BadRequestException,
  );
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
