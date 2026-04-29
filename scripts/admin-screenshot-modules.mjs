#!/usr/bin/env node

import { mkdir, rm, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { chromium } from 'playwright';

const adminBaseUrl = process.env.ADMIN_BASE_URL || 'http://localhost:5173';
const backendBaseUrl = process.env.BACKEND_BASE_URL || 'http://127.0.0.1:3010';
const phone = process.env.SMOKE_PHONE || '13800138000';
const password = process.env.SMOKE_PASSWORD || '123456';
const outDir = resolve(process.env.ADMIN_SCREENSHOT_DIR || 'artifacts/admin-screenshots');
const headed = process.env.HEADED === '1';

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
  if (!response.ok) {
    throw new Error(`${path} HTTP ${response.status}: ${text.slice(0, 300)}`);
  }
  const body = text ? JSON.parse(text) : null;
  if (body && typeof body === 'object' && 'code' in body) {
    if (body.code !== 0) {
      throw new Error(`${path} API code ${body.code}: ${body.message || ''}`);
    }
    return body.data;
  }
  return body;
}

async function loadFixture() {
  const banks = await requestJson(backendBaseUrl, '/api/banks?page=1&pageSize=50');
  const bank = banks.list.find((item) => Number(item.total_count) > 0) || banks.list[0];
  if (!bank?.id) throw new Error('No bank found for Admin screenshots');

  const questions = await requestJson(
    backendBaseUrl,
    `/api/questions?bankId=${encodeURIComponent(bank.id)}&page=1&pageSize=20`,
  );
  const question = questions.list?.[0];

  return {
    bankId: bank.id,
    bankName: bank.name,
    questionId: question?.id || '',
  };
}

async function loginAdmin(page) {
  await page.goto(toUrl(adminBaseUrl, '/login'), { waitUntil: 'domcontentloaded' });
  await page.locator('.el-form-item').filter({ hasText: '手机号' }).locator('input').fill(phone);
  await page.locator('.el-form-item').filter({ hasText: '密码' }).locator('input[type="password"]').fill(password);
  await Promise.all([
    page.waitForURL(/\/dashboard$/, { timeout: 15000 }),
    page.getByRole('button', { name: '登录' }).click(),
  ]);
  await page.getByText('刷题管理', { exact: false }).first().waitFor({ state: 'visible', timeout: 15000 });
}

async function settle(page) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(700);
  await page.locator('.el-loading-mask').first().waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(300);
}

async function screenshotRoute(page, shot, manifest) {
  const url = toUrl(adminBaseUrl, shot.path);
  const startedAt = new Date().toISOString();
  const file = `${shot.order.toString().padStart(2, '0')}-${shot.slug}.png`;
  const path = join(outDir, file);
  const errorsBefore = manifest.consoleErrors.length;

  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await settle(page);
  if (shot.waitForText) {
    await page.getByText(shot.waitForText, { exact: false }).first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
  }
  if (shot.waitForSelector) {
    await page.locator(shot.waitForSelector).first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
  }
  await page.screenshot({ path, fullPage: true });

  manifest.shots.push({
    order: shot.order,
    title: shot.title,
    route: shot.path,
    file,
    url,
    startedAt,
    finishedAt: new Date().toISOString(),
    consoleErrors: manifest.consoleErrors.slice(errorsBefore),
  });
}

async function main() {
  await rm(outDir, { recursive: true, force: true });
  await mkdir(outDir, { recursive: true });

  const fixture = await loadFixture();
  const routes = [
    { order: 1, slug: 'login', title: '登录页', path: '/login', waitForText: '管理员登录' },
    { order: 2, slug: 'dashboard', title: '首页仪表盘', path: '/dashboard', waitForText: '首页' },
    { order: 3, slug: 'banks', title: '题库管理', path: '/banks', waitForSelector: '.el-table__body' },
    { order: 4, slug: 'bank-create', title: '新建题库', path: '/banks/create', waitForText: '题库' },
    { order: 5, slug: 'bank-edit', title: '编辑题库', path: `/banks/${fixture.bankId}/edit`, waitForText: '题库' },
    { order: 6, slug: 'bank-upload', title: 'PDF 上传解析', path: `/banks/${fixture.bankId}/upload`, waitForText: '上传题库 PDF' },
    { order: 7, slug: 'bank-questions', title: '题目列表', path: `/banks/${fixture.bankId}/questions`, waitForText: '进入审核' },
    { order: 8, slug: 'bank-review', title: '题目审核编辑', path: `/banks/${fixture.bankId}/review`, waitForText: '待审核' },
    { order: 9, slug: 'answer-book', title: '解析册匹配', path: `/banks/${fixture.bankId}/answer-book`, waitForText: '题册与解析册' },
    { order: 10, slug: 'materials', title: '材料管理', path: '/materials', waitForText: '材料' },
    { order: 11, slug: 'pdf-tasks', title: '解析任务', path: '/pdf/tasks', waitForText: '解析任务' },
    { order: 12, slug: 'users', title: '用户管理', path: '/users', waitForText: '用户' },
    { order: 13, slug: 'system-basic', title: '系统设置-基础配置', path: '/system', waitForText: '系统配置' },
  ];

  if (fixture.questionId) {
    routes.splice(9, 0, {
      order: 9,
      slug: 'question-preview',
      title: '题目预览与 PDF 框选',
      path: `/banks/${fixture.bankId}/questions/${fixture.questionId}/preview`,
      waitForText: '题目预览',
    });
  }

  for (let index = 0; index < routes.length; index += 1) {
    routes[index].order = index + 1;
  }

  const manifest = {
    generatedAt: new Date().toISOString(),
    adminBaseUrl,
    backendBaseUrl,
    fixture,
    shots: [],
    consoleErrors: [],
    pageErrors: [],
  };

  const browser = await chromium.launch({ headless: !headed });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 950 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();

  page.on('console', (message) => {
    if (message.type() === 'error') {
      manifest.consoleErrors.push({
        text: message.text(),
        url: page.url(),
        at: new Date().toISOString(),
      });
    }
  });
  page.on('pageerror', (error) => {
    manifest.pageErrors.push({
      message: error.message,
      url: page.url(),
      at: new Date().toISOString(),
    });
  });

  try {
    await loginAdmin(page);
    for (const route of routes) {
      await screenshotRoute(page, route, manifest);
    }
  } finally {
    await context.close();
    await browser.close();
  }

  await writeFile(join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
  await writeFile(
    join(outDir, 'README.md'),
    [
      '# Admin 模块截图',
      '',
      `生成时间：${manifest.generatedAt}`,
      `Admin 地址：${adminBaseUrl}`,
      `题库样例：${fixture.bankName} (${fixture.bankId})`,
      '',
      '## 截图清单',
      '',
      ...manifest.shots.map((shot) => `- ${shot.order}. ${shot.title}: \`${shot.file}\` (${shot.route})`),
      '',
      `Console errors: ${manifest.consoleErrors.length}`,
      `Page errors: ${manifest.pageErrors.length}`,
      '',
    ].join('\n'),
  );

  console.log(`Saved ${manifest.shots.length} screenshots to ${outDir}`);
  console.log(`Console errors: ${manifest.consoleErrors.length}`);
  console.log(`Page errors: ${manifest.pageErrors.length}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
