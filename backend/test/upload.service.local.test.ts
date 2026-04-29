import * as assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { rm } from 'node:fs/promises';
import { join } from 'node:path';
import { UploadService } from '../src/modules/upload/upload.service';

const uploadsDir = join(process.cwd(), 'uploads');

function service() {
  return new UploadService({
    get: (key: string, fallback?: string) => {
      const values: Record<string, string> = {
        UPLOAD_PROVIDER: 'local',
        BACKEND_URL: 'http://127.0.0.1:3010',
      };
      return values[key] ?? fallback;
    },
  } as any);
}

async function run() {
  await cleanup();
  await testLocalProviderUploadsFile();
  await cleanup();
}

async function testLocalProviderUploadsFile() {
  const svc = service();
  const result = await svc.uploadFile({
    originalname: 'smoke.pdf',
    mimetype: 'application/pdf',
    buffer: Buffer.from('local-upload-smoke'),
  } as Express.Multer.File);

  assert.match(result.url, /^http:\/\/127\.0\.0\.1:3010\/uploads\//);
  assert.equal(result.filename, 'smoke.pdf');

  const pathname = new URL(result.url).pathname.replace(/^\/uploads\//, '');
  assert.equal(existsSync(join(uploadsDir, pathname)), true);
}

async function cleanup() {
  await rm(uploadsDir, { recursive: true, force: true });
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
