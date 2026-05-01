#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const SOURCE_FULL_PDF = process.env.SOURCE_FULL_PDF || '/Users/apple/Downloads/题本篇.pdf';
const MAIN_TEST_PDF = process.env.MAIN_TEST_PDF || '/Users/apple/Downloads/题本篇-1-8.pdf';
const PARTIAL_CONTEXT_NEGATIVE_PDF =
  process.env.PARTIAL_CONTEXT_NEGATIVE_PDF || '/Users/apple/Downloads/公考/project2/backend/sample-题本篇-3-7.pdf';
const OUTPUT_DIR = process.env.OUTPUT_DIR || defaultOutputDir();

function defaultOutputDir() {
  const now = new Date();
  const stamp = [
    now.getFullYear(),
    `${now.getMonth() + 1}`.padStart(2, '0'),
    `${now.getDate()}`.padStart(2, '0'),
    '-',
    `${now.getHours()}`.padStart(2, '0'),
    `${now.getMinutes()}`.padStart(2, '0'),
    `${now.getSeconds()}`.padStart(2, '0'),
  ].join('');
  return `/Users/apple/Downloads/公考/project2/debug/paper-review/${stamp}`;
}

function pdfInfo(filePath) {
  const script = `
import json
import pathlib
import sys

try:
    import fitz
except Exception as exc:
    print(json.dumps({"path": sys.argv[1], "exists": pathlib.Path(sys.argv[1]).exists(), "error": f"fitz_import_failed: {exc}"}))
    sys.exit(0)

path = pathlib.Path(sys.argv[1])
if not path.exists():
    print(json.dumps({"path": str(path), "exists": False}))
    sys.exit(0)

try:
    with fitz.open(path) as doc:
        print(json.dumps({
            "path": str(path),
            "exists": True,
            "page_count": doc.page_count,
            "bytes": path.stat().st_size,
        }, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"path": str(path), "exists": True, "error": str(exc)}, ensure_ascii=False))
`;

  const result = spawnSync('python3', ['-c', script, filePath], { encoding: 'utf8' });
  if (result.error) {
    return { path: filePath, exists: false, error: result.error.message };
  }
  if (result.status !== 0) {
    return { path: filePath, exists: false, error: result.stderr.trim() || `python exited ${result.status}` };
  }
  return JSON.parse(result.stdout.trim());
}

function generateMainFixtureIfMissing(sourcePath, outputPath) {
  if (existsSync(outputPath)) return { generated: false };
  if (!existsSync(sourcePath)) {
    return { generated: false, error: `主测试 PDF 不存在且源 PDF 不存在：${sourcePath}` };
  }
  const script = `
import pathlib
import sys

import fitz

source_path = pathlib.Path(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])
with fitz.open(source_path) as source:
    if source.page_count < 8:
        raise SystemExit(f"源 PDF 页数不足 8 页：{source.page_count}")
    target = fitz.open()
    target.insert_pdf(source, from_page=0, to_page=7)
    target.save(output_path)
    target.close()
`;
  const result = spawnSync('python3', ['-c', script, sourcePath, outputPath], { encoding: 'utf8' });
  if (result.status !== 0 || result.error) {
    return {
      generated: false,
      error: result.error?.message || result.stderr.trim() || `python exited ${result.status}`,
    };
  }
  return { generated: true };
}

const source = pdfInfo(SOURCE_FULL_PDF);
const generation = generateMainFixtureIfMissing(SOURCE_FULL_PDF, MAIN_TEST_PDF);
const main = pdfInfo(MAIN_TEST_PDF);
const partial = pdfInfo(PARTIAL_CONTEXT_NEGATIVE_PDF);

const failures = [];
if (!source.exists) failures.push(`源 PDF 不存在：${SOURCE_FULL_PDF}`);
if (source.error) failures.push(`源 PDF 无法读取：${source.error}`);
if (source.page_count < 8) failures.push(`源 PDF 页数不足 8 页：${source.page_count ?? 'unknown'}`);
if (generation.error) failures.push(generation.error);

if (!main.exists) failures.push(`主测试 PDF 不存在：${MAIN_TEST_PDF}`);
if (main.error) failures.push(`主测试 PDF 无法读取：${main.error}`);
if (main.page_count !== 8) failures.push(`主测试 PDF 必须为 8 页，实际为：${main.page_count ?? 'unknown'}`);
if (main.path === partial.path) failures.push('主测试 PDF 不能与 partial context 负样例共用同一路径');

if (!partial.exists) failures.push(`partial context 负样例不存在：${PARTIAL_CONTEXT_NEGATIVE_PDF}`);
if (partial.error) failures.push(`partial context 负样例无法读取：${partial.error}`);
if (partial.page_count !== 5) failures.push(`partial context 负样例应为第 3-7 页截取，共 5 页，实际为：${partial.page_count ?? 'unknown'}`);

const report = {
  checkedAt: new Date().toISOString(),
  ok: failures.length === 0,
  failures,
  fixtures: {
    mainFixture: {
      ...main,
      pageCount: main.page_count ?? null,
      role: 'main_positive_fixture',
      generated: Boolean(generation.generated),
      generatedFrom: {
        sourcePdf: SOURCE_FULL_PDF,
        pageRange: '1-8',
      },
      expected: {
        partialPdfContextAllowed: false,
        missingPreviousPageContextAllowed: false,
        manualForceAddAllowed: 'only_when_source_and_material_are_reviewable',
      },
    },
    negativeFixture: {
      ...partial,
      pageCount: partial.page_count ?? null,
      role: 'partial_pdf_context_negative_regression',
      expected: {
        canAutoIngest: false,
        canAutoCompose: false,
        manualForceAddAllowed: false,
        manualReviewable: false,
        mustShowMissingContextReason: true,
        mustNotBeAiPassed: true,
        expectedRiskTags: ['partial_pdf_context', 'missing_previous_page_context'],
        expectedAction: '补齐上一页或使用完整 PDF 重新解析',
      },
    },
  },
};

mkdirSync(OUTPUT_DIR, { recursive: true });
writeFileSync(path.join(OUTPUT_DIR, 'pdf-fixtures-check.json'), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));

if (failures.length) {
  process.exitCode = 1;
}
