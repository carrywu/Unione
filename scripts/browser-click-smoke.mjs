#!/usr/bin/env node

import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { chromium } from 'playwright';

const backendBaseUrl = process.env.BACKEND_BASE_URL || 'http://127.0.0.1:3010';
const h5BaseUrl = process.env.H5_BASE_URL || 'http://127.0.0.1:5174';
const adminBaseUrl = process.env.ADMIN_BASE_URL || 'http://127.0.0.1:5173';
const phone = process.env.SMOKE_PHONE || '13800138000';
const password = process.env.SMOKE_PASSWORD || '123456';
const headed = process.env.HEADED === '1';
const artifactsDir = process.env.BROWSER_SMOKE_ARTIFACTS || 'artifacts/browser-smoke';

const results = [];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function toUrl(base, path) {
  return new URL(path, base).toString();
}

async function requestJson(base, path, options = {}) {
  const response = await fetch(toUrl(base, path), {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
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

async function loadFixture() {
  const login = await requestJson(backendBaseUrl, '/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ phone, password }),
  });
  const token = login.access_token;
  assert(token, 'login did not return access_token');
  const auth = { Authorization: `Bearer ${token}` };

  const banks = await requestJson(backendBaseUrl, '/api/banks?page=1&pageSize=20');
  const bank = banks.list.find((item) => Number(item.total_count) > 0) || banks.list[0];
  assert(bank?.id, 'no bank available for browser smoke');
  const questions = await requestJson(
    backendBaseUrl,
    `/api/questions?bankId=${encodeURIComponent(bank.id)}&page=1&pageSize=5`,
  );
  const question = questions.list?.[0];
  assert(question?.id, 'no question available for browser smoke');

  const answer = await requestJson(backendBaseUrl, `/api/questions/${question.id}/answer`, { headers: auth });
  const wrongAnswer = chooseWrongAnswer(question, answer.answer);
  await requestJson(backendBaseUrl, '/api/records/submit', {
    method: 'POST',
    headers: auth,
    body: JSON.stringify({
      question_id: question.id,
      user_answer: wrongAnswer,
      time_spent: 1,
    }),
  });

  return { bankId: bank.id, questionId: question.id };
}

function chooseWrongAnswer(question, answer) {
  if (question.type === 'judge') return answer === 'T' ? 'F' : 'T';
  return ['A', 'B', 'C', 'D'].find((item) => item !== answer && question[`option_${item.toLowerCase()}`]) || 'A';
}

async function clickAndExpectUrl(page, locator, pattern, label) {
  await Promise.all([
    page.waitForURL(pattern, { timeout: 10000 }),
    locator.click(),
  ]);
  results.push(`PASS ${label}`);
}

async function expectVisible(page, selectorOrText, label) {
  const locator = selectorOrText.startsWith?.('.') || selectorOrText.startsWith?.('#')
    ? page.locator(selectorOrText)
    : page.getByText(selectorOrText, { exact: false });
  await locator.first().waitFor({ state: 'visible', timeout: 10000 });
  results.push(`PASS ${label}`);
}

function attachPageGuards(page, label) {
  const pageErrors = [];
  page.on('pageerror', (error) => {
    pageErrors.push(error.message);
  });
  return () => {
    assert(pageErrors.length === 0, `${label} page errors:\n${pageErrors.join('\n')}`);
  };
}

async function loginH5(page) {
  await page.goto(toUrl(h5BaseUrl, '/login'));
  await page.locator('#phone').fill(phone);
  await page.locator('#password').fill(password);
  await clickAndExpectUrl(page, page.getByRole('button', { name: /^登录$/ }), /\/$/, 'h5 login');
  await expectVisible(page, '公考刷题', 'h5 home visible');
}

async function runH5(browser, fixture) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
  });
  const page = await context.newPage();
  const assertNoPageErrors = attachPageGuards(page, 'h5');
  try {
    await loginH5(page);

    await clickAndExpectUrl(
      page,
      page.locator('.bottom-nav button').filter({ hasText: '题库' }),
      /\/bank$/,
      'h5 bottom nav to bank',
    );
    await expectVisible(page, '.essay-card', 'h5 bank cards visible');
    await clickAndExpectUrl(page, page.locator('.essay-card').first(), /\/quiz\/[^/]+$/, 'h5 bank card opens quiz');
    await expectVisible(page, '智能练习', 'h5 quiz visible');

    await page.goto(toUrl(h5BaseUrl, '/wrong'));
    await expectVisible(page, '错题解析', 'h5 wrong page visible');
    await clickAndExpectUrl(
      page,
      page.getByRole('button', { name: '随机练习' }),
      /\/quiz\/[^/]+$/,
      'h5 wrong random practice opens quiz',
    );

    await page.goto(toUrl(h5BaseUrl, '/'));
    await expectVisible(page, '智能推荐', 'h5 recommendations visible');
    await page.locator('.rec-card').first().click();
    await page.waitForURL(/\/quiz\/[^/]+$|\/bank$/, { timeout: 10000 });
    results.push('PASS h5 recommendation card navigates');

    await page.goto(toUrl(h5BaseUrl, `/quiz/${fixture.bankId}`));
    await expectVisible(page, '.option-card', 'h5 quiz options visible');
    await page.locator('.option-card').first().click();
    await page.getByRole('button', { name: /提交答案/ }).click();
    await expectVisible(page, '解析详情', 'h5 submit answer shows analysis');

    assertNoPageErrors();
  } catch (error) {
    await page.screenshot({ path: join(artifactsDir, 'h5-failure.png'), fullPage: true }).catch(() => {});
    throw error;
  } finally {
    await context.close();
  }
}

async function loginAdmin(page) {
  await page.goto(toUrl(adminBaseUrl, '/login'));
  await page.locator('.el-form-item').filter({ hasText: '手机号' }).locator('input').fill(phone);
  await page.locator('.el-form-item').filter({ hasText: '密码' }).locator('input[type="password"]').fill(password);
  await clickAndExpectUrl(page, page.getByRole('button', { name: '登录' }), /\/dashboard$/, 'admin login');
  await expectVisible(page, '刷题管理', 'admin shell visible');
}

async function runAdmin(browser) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await context.newPage();
  const assertNoPageErrors = attachPageGuards(page, 'admin');
  try {
    await loginAdmin(page);
    await clickAndExpectUrl(
      page,
      page.locator('.el-menu-item').filter({ hasText: '题库管理' }),
      /\/banks$/,
      'admin sidebar to banks',
    );
    await expectVisible(page, '.el-table__body', 'admin bank table visible');

    await clickAndExpectUrl(
      page,
      page.locator('.el-table__body .el-button.is-link').first(),
      /\/banks\/[^/]+\/questions$/,
      'admin bank name opens questions',
    );
    await expectVisible(page, '进入审核', 'admin questions page visible');

    await clickAndExpectUrl(
      page,
      page.getByRole('button', { name: 'PDF定位' }).first(),
      /\/banks\/[^/]+\/questions\/[^/]+\/preview$/,
      'admin PDF preview opens',
    );
    await expectVisible(page, '题目预览', 'admin preview page visible');

    await page.goto(toUrl(adminBaseUrl, '/banks'));
    await expectVisible(page, '.el-table__body', 'admin bank table visible again');
    await clickAndExpectUrl(
      page,
      page.getByRole('button', { name: '解析册匹配' }).first(),
      /\/banks\/[^/]+\/answer-book$/,
      'admin answer-book page opens',
    );
    await expectVisible(page, '题册与解析册', 'admin answer-book visible');

    assertNoPageErrors();
  } catch (error) {
    await page.screenshot({ path: join(artifactsDir, 'admin-failure.png'), fullPage: true }).catch(() => {});
    throw error;
  } finally {
    await context.close();
  }
}

async function main() {
  await mkdir(artifactsDir, { recursive: true });
  const fixture = await loadFixture();
  const browser = await chromium.launch({ headless: !headed });
  try {
    await runH5(browser, fixture);
    await runAdmin(browser);
  } catch (error) {
    console.error(`Browser click smoke failed: ${error.message}`);
    throw error;
  } finally {
    await browser.close();
  }

  console.log('Browser click smoke passed');
  for (const item of results) console.log(item);
}

main().catch(() => {
  process.exitCode = 1;
});
