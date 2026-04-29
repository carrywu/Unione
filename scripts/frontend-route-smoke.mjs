#!/usr/bin/env node

const backendBaseUrl = process.env.BACKEND_BASE_URL || 'http://127.0.0.1:3010';
const h5BaseUrl = process.env.H5_BASE_URL || 'http://127.0.0.1:5174';
const adminBaseUrl = process.env.ADMIN_BASE_URL || 'http://127.0.0.1:5173';
const phone = process.env.SMOKE_PHONE || '13800138000';
const password = process.env.SMOKE_PASSWORD || '123456';
const appArg = process.argv.find((arg) => arg.startsWith('--app='))?.split('=')[1] || 'all';
const timeoutMs = Number(process.env.SMOKE_TIMEOUT_MS || 10000);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function toUrl(base, path) {
  return new URL(path, base).toString();
}

async function getJson(base, path, options = {}) {
  const response = await fetch(toUrl(base, path), {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const text = await response.text();
  assert(response.ok, `${path} HTTP ${response.status}: ${text.slice(0, 300)}`);
  const body = text ? JSON.parse(text) : null;
  if (body && typeof body === 'object' && 'code' in body) {
    assert(body.code === 0, `${path} API code ${body.code}: ${body.message || ''}`);
    return body.data;
  }
  return body;
}

async function getHtml(base, path) {
  const response = await fetch(toUrl(base, path), {
    headers: { Accept: 'text/html' },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const contentType = response.headers.get('content-type') || '';
  const text = await response.text();
  assert(response.ok, `${path} HTTP ${response.status}: ${text.slice(0, 300)}`);
  assert(contentType.includes('text/html'), `${path} did not return html: ${contentType}`);
  assert(text.includes('<div id="app"></div>'), `${path} missing Vue mount node`);
  assert(text.includes('/src/main.ts') || text.includes('assets/index-'), `${path} missing app entry`);
}

async function loadFixtureIds() {
  const login = await getJson(backendBaseUrl, '/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ phone, password }),
  });
  const token = login.access_token;
  assert(token, 'login did not return access_token');
  const banks = await getJson(backendBaseUrl, '/api/banks?page=1&pageSize=20');
  const bank = banks.list.find((item) => Number(item.total_count) > 0) || banks.list[0];
  assert(bank?.id, 'no bank id available for route smoke');
  const questions = await getJson(
    backendBaseUrl,
    `/api/questions?bankId=${encodeURIComponent(bank.id)}&page=1&pageSize=1`,
  );
  return { token, bankId: bank.id, questionId: questions.list?.[0]?.id || '' };
}

async function smokeH5(token, bankId) {
  const routes = ['/', '/login', '/register', '/bank', `/bank/${bankId}`, `/quiz/${bankId}`, '/wrong', '/profile', '/result', '/analysis'];
  for (const route of routes) {
    await getHtml(h5BaseUrl, route);
    console.log(`PASS h5 route ${route}`);
  }
  await getJson(h5BaseUrl, '/api/banks?page=1&pageSize=1');
  console.log('PASS h5 proxy /api/banks');
  await getJson(h5BaseUrl, '/api/wrong/practice?count=1', {
    headers: { Authorization: `Bearer ${token}` },
  });
  console.log('PASS h5 proxy /api/wrong/practice');
}

async function smokeAdmin(token, bankId, questionId) {
  const routes = [
    '/',
    '/login',
    '/dashboard',
    '/banks',
    `/banks/${bankId}/questions`,
    `/banks/${bankId}/review`,
    `/banks/${bankId}/answer-book`,
    '/pdf/tasks',
    '/workbench',
    '/materials',
    '/users',
    '/system',
  ];
  if (questionId) routes.push(`/banks/${bankId}/questions/${questionId}/preview`);
  for (const route of routes) {
    await getHtml(adminBaseUrl, route);
    console.log(`PASS admin route ${route}`);
  }
  await getJson(adminBaseUrl, '/admin/banks?page=1&pageSize=1', {
    headers: { Authorization: `Bearer ${token}` },
  });
  console.log('PASS admin proxy /admin/banks');
}

async function main() {
  const { token, bankId, questionId } = await loadFixtureIds();
  if (appArg === 'all' || appArg === 'h5') await smokeH5(token, bankId);
  if (appArg === 'all' || appArg === 'admin') await smokeAdmin(token, bankId, questionId);
  console.log('Frontend route smoke passed');
}

main().catch((error) => {
  console.error(`Frontend route smoke failed: ${error.message}`);
  process.exitCode = 1;
});
