#!/usr/bin/env node

const backendBaseUrl = process.env.BACKEND_BASE_URL || 'http://127.0.0.1:3010';
const phone = process.env.SMOKE_PHONE || '13800138000';
const password = process.env.SMOKE_PASSWORD || '123456';
const timeoutMs = Number(process.env.SMOKE_TIMEOUT_MS || 10000);

const results = [];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function url(path) {
  return new URL(path, backendBaseUrl).toString();
}

async function request(name, path, options = {}) {
  const startedAt = Date.now();
  const response = await fetch(url(path), {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const text = await response.text();
  let body;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  assert(response.ok, `${name} HTTP ${response.status}: ${text.slice(0, 300)}`);
  if (body && typeof body === 'object' && 'code' in body) {
    assert(body.code === 0, `${name} API code ${body.code}: ${body.message || ''}`);
    body = body.data;
  }
  results.push({ name, ms: Date.now() - startedAt });
  return body;
}

async function main() {
  const login = await request('auth login', '/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ phone, password }),
  });
  const token = login.access_token;
  assert(token, 'auth login did not return access_token');
  const auth = { Authorization: `Bearer ${token}` };

  const banks = await request('public bank list', '/api/banks?page=1&pageSize=20');
  assert(Array.isArray(banks.list), 'bank list is not an array');
  assert(banks.list.length > 0, 'no published banks available for smoke test');

  const bank = banks.list.find((item) => Number(item.total_count) > 0) || banks.list[0];
  assert(bank?.id, 'bank id missing');

  await request('user stats overview', '/api/stats/overview', { headers: auth });
  await request('user selected books', '/api/user/question-books', { headers: auth });
  await request('wrong stats', '/api/wrong/stats', { headers: auth });
  await request('wrong random practice', '/api/wrong/practice?count=20', { headers: auth });

  const questions = await request(
    'published questions by bank',
    `/api/questions?bankId=${encodeURIComponent(bank.id)}&page=1&pageSize=5`,
  );
  assert(Array.isArray(questions.list), 'question list is not an array');

  if (questions.list[0]?.id) {
    await request('question answer detail', `/api/questions/${questions.list[0].id}/answer`, {
      headers: auth,
    });
  }

  await request('admin stats overview', '/admin/stats/overview', { headers: auth });
  await request('admin bank list', '/admin/banks?page=1&pageSize=5', { headers: auth });
  await request(
    'admin question list',
    `/admin/questions?bankId=${encodeURIComponent(bank.id)}&page=1&pageSize=5`,
    { headers: auth },
  );

  console.log(`Backend smoke passed (${backendBaseUrl})`);
  for (const item of results) {
    console.log(`PASS ${item.name} ${item.ms}ms`);
  }
}

main().catch((error) => {
  console.error(`Backend smoke failed: ${error.message}`);
  process.exitCode = 1;
});
