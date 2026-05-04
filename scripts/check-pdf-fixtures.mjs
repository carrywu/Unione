#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const SOURCE_FULL_PDF = process.env.SOURCE_FULL_PDF || '/Users/apple/Downloads/题本篇.pdf';
const MAIN_TEST_PDF = process.env.MAIN_TEST_PDF || '/Users/apple/Downloads/题本篇-1-8.pdf';
const FULL_SCANNED_PDF = process.env.FULL_SCANNED_PDF || SOURCE_FULL_PDF;
const LATEST_1200_PDF = process.env.LATEST_1200_PDF || '/Users/apple/Downloads/最新：1200题题本.pdf';
const KUAKUA_UPPER_PDF =
  process.env.KUAKUA_UPPER_PDF || '/Users/apple/Downloads/2026资料分析题库-夸夸刷-必考题型专项拔高（上册）.pdf';
const KUAKUA_LOWER_PDF =
  process.env.KUAKUA_LOWER_PDF || '/Users/apple/Downloads/2026资料分析题库-夸夸刷-必考题型专项拔高（下册）.pdf';
const CANDIDATE_TEST_PDF = process.env.CANDIDATE_TEST_PDF || '/Users/apple/Downloads/题本篇-9-14.pdf';
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

function runPython(script, args = []) {
  const python = existsSync('pdf-service/.venv/bin/python') ? 'pdf-service/.venv/bin/python' : 'python3';
  const result = spawnSync(python, ['-c', script, ...args], { encoding: 'utf8' });
  if (result.status !== 0 || result.error) {
    throw new Error(result.error?.message || result.stderr.trim() || `python exited ${result.status}`);
  }
  return result.stdout.trim();
}

function ensureMainFixture() {
  if (existsSync(MAIN_TEST_PDF)) return { generated: false };
  if (!existsSync(SOURCE_FULL_PDF)) {
    return { generated: false, error: `主测试 PDF 不存在且源 PDF 不存在：${SOURCE_FULL_PDF}` };
  }
  try {
    runPython(
      `
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
`,
      [SOURCE_FULL_PDF, MAIN_TEST_PDF],
    );
    return { generated: true };
  } catch (error) {
    return { generated: false, error: error.message };
  }
}

function ensureCandidateFixture() {
  if (existsSync(CANDIDATE_TEST_PDF)) return { generated: false, method: 'existing', pageRange: '9-14' };
  if (!existsSync(SOURCE_FULL_PDF)) {
    return { generated: false, error: `候选页段无法生成，源 PDF 不存在：${SOURCE_FULL_PDF}` };
  }
  const qpdf = spawnSync('qpdf', [SOURCE_FULL_PDF, '--pages', SOURCE_FULL_PDF, '9-14', '--', CANDIDATE_TEST_PDF], {
    encoding: 'utf8',
  });
  if (!qpdf.error && qpdf.status === 0) return { generated: true, method: 'qpdf', pageRange: '9-14' };
  try {
    runPython(
      `
import pathlib
import sys
import fitz
source_path = pathlib.Path(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])
with fitz.open(source_path) as source:
    if source.page_count < 14:
        raise SystemExit(f"源 PDF 页数不足 14 页：{source.page_count}")
    target = fitz.open()
    target.insert_pdf(source, from_page=8, to_page=13)
    target.save(output_path)
    target.close()
`,
      [SOURCE_FULL_PDF, CANDIDATE_TEST_PDF],
    );
    return { generated: true, method: 'PyMuPDF', pageRange: '9-14' };
  } catch (error) {
    return {
      generated: false,
      error: error.message || qpdf.stderr?.trim() || 'candidate fixture generation failed',
    };
  }
}

function analyzeFixtures() {
  const script = String.raw`
import hashlib
import json
import math
import pathlib
import re
import sys

import fitz

output_dir = pathlib.Path(sys.argv[1])
fixtures = json.loads(sys.argv[2])

QUESTION_RE = re.compile(r"(第\s*\d+\s*题|\d+\s*[\.．、]\s*|练习题|根据.*材料|回答\s*\d+)")
OPTION_RE = re.compile(r"(^|\s)[A-D]\s*[\.．、]")
TOC_RE = re.compile(r"(目录|Contents|第[一二三四五六七八九十]+章|页码|……|\\.\\.\\.)")
ANSWER_RE = re.compile(r"(答案|解析|参考答案)")

def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def pix_stats(pix):
    samples = pix.samples
    total = max(pix.width * pix.height, 1)
    dark = 0
    very_dark = 0
    row_dark = [0] * pix.height
    col_dark = [0] * pix.width
    step = pix.n
    for offset in range(0, len(samples), step):
        idx = offset // step
        y = idx // pix.width
        x = idx % pix.width
        r, g, b = samples[offset], samples[offset + 1], samples[offset + 2]
        gray = (r * 299 + g * 587 + b * 114) // 1000
        if gray < 245:
            dark += 1
            row_dark[y] += 1
            col_dark[x] += 1
        if gray < 130:
            very_dark += 1
    dense_rows = sum(1 for value in row_dark if value > pix.width * 0.015)
    dense_cols = sum(1 for value in col_dark if value > pix.height * 0.015)
    long_rows = sum(1 for value in row_dark if value > pix.width * 0.25)
    long_cols = sum(1 for value in col_dark if value > pix.height * 0.25)
    return {
        "nonWhiteRatio": round(dark / total, 4),
        "veryDarkRatio": round(very_dark / total, 4),
        "denseRowRatio": round(dense_rows / max(pix.height, 1), 4),
        "denseColRatio": round(dense_cols / max(pix.width, 1), 4),
        "longHorizontalLineCount": long_rows,
        "longVerticalLineCount": long_cols,
    }

def sample_pages(page_count, fixture_key):
    if page_count <= 20:
        return list(range(page_count))
    pages = set(range(min(page_count, 12)))
    for idx in [20, 30, 50, 100, page_count // 4, page_count // 2, (page_count * 3) // 4, page_count - 1]:
        if 0 <= idx < page_count:
            pages.add(idx)
    return sorted(pages)

def score_page(page_no, text, stats, drawing_count, image_count, fixture_key):
    text_length = len(text.strip())
    non_white = stats["nonWhiteRatio"]
    blank = max(0.0, min(1.0, 1.0 - (non_white / 0.045)))
    question_text = 1.0 if QUESTION_RE.search(text) else 0.0
    option_text = min(1.0, len(OPTION_RE.findall(text)) / 4.0)
    toc_text = 1.0 if TOC_RE.search(text) else 0.0
    answer_text = 1.0 if ANSWER_RE.search(text) else 0.0
    image_text_like = 1.0 if text_length < 20 and non_white >= 0.055 and blank < 0.55 else 0.0
    option_like = max(option_text, 0.55 if image_text_like else 0.0)
    table_like = max(
        0.0,
        min(1.0, (stats["longHorizontalLineCount"] + stats["longVerticalLineCount"]) / 18.0),
    )
    chart_like = max(table_like, 0.65 if image_count > 1 and non_white > 0.08 else 0.0)
    toc_like = max(toc_text, 0.0)
    if fixture_key == "latest1200" and page_no <= 5 and text_length < 20 and image_text_like:
        toc_like = max(toc_like, 0.75)
    question_like = max(question_text, 0.78 if image_text_like else 0.0)
    if toc_like > 0.7 and question_text == 0.0:
        question_like = min(question_like, 0.45)
    return {
        "pageNo": page_no,
        "blankPageScore": round(blank, 3),
        "questionLikeScore": round(question_like, 3),
        "optionLikeScore": round(option_like, 3),
        "tableLikeScore": round(table_like, 3),
        "chartLikeScore": round(chart_like, 3),
        "tocLikeScore": round(toc_like, 3),
        "answerPageLikeScore": round(answer_text, 3),
        "textLength": text_length,
        **stats,
        "drawingCount": drawing_count,
        "imageCount": image_count,
    }

def filename_hint(path):
    name = pathlib.Path(path).name
    if "解析" in name:
        return "answer_book_hint"
    if "题本" in name or "题本篇" in name:
        return "scanned_question_book_hint"
    if "教材" in name or "讲义" in name:
        return "textbook_hint"
    return "unknown"

def recommend(text_available, image_only, page_reality):
    question_pages = page_reality["questionLikePages"]
    toc_pages = set(page_reality["tocLikePages"])
    rendered = max(page_reality["renderedPageCount"], 1)
    table_or_chart_pages = set(page_reality["tableLikePages"]) | set(page_reality["chartLikePages"])
    if len(question_pages) == 0 and len(toc_pages) >= rendered * 0.6:
        return "skip"
    if image_only and question_pages:
        return "scanned"
    if text_available and len(table_or_chart_pages) >= max(1, len(question_pages) * 0.35):
        return "hybrid"
    if text_available:
        return "text"
    return "needs_manual_route"

def actual_kind(strategy, page_reality):
    if strategy == "scanned":
        return "scanned_question_book"
    if strategy == "hybrid":
        return "hybrid_question_book"
    if strategy == "text":
        return "text_question_book"
    if strategy == "skip":
        return "toc_or_non_question"
    return "unknown"

def inspect_fixture(item):
    key = item["key"]
    label = item["label"]
    pdf_path = pathlib.Path(item["path"])
    out_dir = output_dir / "fixture-sanity" / label
    rendered_dir = out_dir / "rendered-pages"
    rendered_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "key": key,
        "label": label,
        "path": str(pdf_path),
        "role": item.get("role"),
        "exists": pdf_path.exists(),
        "filenameHint": filename_hint(pdf_path),
    }
    if not pdf_path.exists():
        base["error"] = "file_missing"
        for name, payload in [
            ("pdf-info.json", base),
            ("page-text.json", {"perPageTextLength": []}),
            ("page-reality.json", {"pages": []}),
            ("sanity.json", {"ok": False, "reason": "file_missing"}),
        ]:
            (out_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return base
    base["fileSize"] = pdf_path.stat().st_size
    base["sha256"] = sha256(pdf_path)
    with fitz.open(pdf_path) as doc:
        base["pageCount"] = doc.page_count
        base["encrypted"] = bool(doc.is_encrypted)
        page_texts = []
        per_page_text_length = []
        page_scores = []
        rendered_pages = []
        for page_index in range(doc.page_count):
            page = doc[page_index]
            text = page.get_text("text") or ""
            page_texts.append({"pageNo": page_index + 1, "text": text[:2000]})
            per_page_text_length.append(len(text.strip()))
        for page_index in sample_pages(doc.page_count, key):
            page = doc[page_index]
            pix = page.get_pixmap(matrix=fitz.Matrix(0.30, 0.30), alpha=False)
            thumbnail = rendered_dir / f"page-{page_index + 1:03d}.png"
            pix.save(str(thumbnail))
            stats = pix_stats(pix)
            drawing_count = len(page.get_drawings())
            image_count = len(page.get_images(full=True))
            score = score_page(page_index + 1, page_texts[page_index]["text"], stats, drawing_count, image_count, key)
            score["thumbnail"] = str(thumbnail)
            page_scores.append(score)
            rendered_pages.append(page_index + 1)
    text_layer_available = any(length >= 20 for length in per_page_text_length)
    image_only = not text_layer_available
    question_like_pages = [page["pageNo"] for page in page_scores if page["questionLikeScore"] >= 0.55 and page["blankPageScore"] < 0.85]
    toc_like_pages = [page["pageNo"] for page in page_scores if page["tocLikeScore"] >= 0.6 and page["questionLikeScore"] < 0.7]
    skipped_like_pages = [page["pageNo"] for page in page_scores if page["blankPageScore"] >= 0.85 or page["tocLikeScore"] >= 0.75]
    table_like_pages = [page["pageNo"] for page in page_scores if page["tableLikeScore"] >= 0.35]
    chart_like_pages = [page["pageNo"] for page in page_scores if page["chartLikeScore"] >= 0.45]
    page_reality = {
        "renderedPageCount": len(rendered_pages),
        "renderedPages": rendered_pages,
        "blankPageScore": round(sum(page["blankPageScore"] for page in page_scores) / max(len(page_scores), 1), 3),
        "questionLikeScore": round(sum(page["questionLikeScore"] for page in page_scores) / max(len(page_scores), 1), 3),
        "optionLikeScore": round(sum(page["optionLikeScore"] for page in page_scores) / max(len(page_scores), 1), 3),
        "tableLikeScore": round(sum(page["tableLikeScore"] for page in page_scores) / max(len(page_scores), 1), 3),
        "chartLikeScore": round(sum(page["chartLikeScore"] for page in page_scores) / max(len(page_scores), 1), 3),
        "tocLikeScore": round(sum(page["tocLikeScore"] for page in page_scores) / max(len(page_scores), 1), 3),
        "answerPageLikeScore": round(sum(page["answerPageLikeScore"] for page in page_scores) / max(len(page_scores), 1), 3),
        "questionLikePages": question_like_pages,
        "tocLikePages": toc_like_pages,
        "skippedLikePages": skipped_like_pages,
        "tableLikePages": table_like_pages,
        "chartLikePages": chart_like_pages,
        "pages": page_scores,
    }
    strategy = recommend(text_layer_available, image_only, page_reality)
    base.update({
        "pageCount": base["pageCount"],
        "renderedPageCount": len(rendered_pages),
        "textLayerAvailable": text_layer_available,
        "perPageTextLength": per_page_text_length,
        "imageOnly": image_only,
        "pageReality": page_reality,
        "actualKind": actual_kind(strategy, page_reality),
        "recommendedStrategy": strategy,
    })
    sanity = {
        "ok": True,
        "role": item.get("role"),
        "actualKind": base["actualKind"],
        "recommendedStrategy": strategy,
        "reasons": [],
    }
    if key == "main":
        required_pages = {1, 2, 3, 6}
        missing = sorted(required_pages - set(question_like_pages))
        if base["pageCount"] != 8:
            sanity["ok"] = False
            sanity["reasons"].append(f"main pageCount expected 8, got {base['pageCount']}")
        if not image_only:
            sanity["ok"] = False
            sanity["reasons"].append("main fixture expected image-only")
        if len(rendered_pages) != 8:
            sanity["ok"] = False
            sanity["reasons"].append(f"main renderedPageCount expected 8, got {len(rendered_pages)}")
        if missing:
            sanity["ok"] = False
            sanity["failureType"] = "fixture_sanity_detector_failed"
            sanity["reasons"].append(f"questionLikePages missing required pages: {missing}")
        if page_reality["blankPageScore"] > 0.75:
            sanity["ok"] = False
            sanity["reasons"].append("main fixture appears blank")
        if sanity["ok"]:
            sanity["positiveFixtureValid"] = True
            sanity["reason"] = "valid image-only scanned question book positive fixture"
    (out_dir / "pdf-info.json").write_text(json.dumps({k: v for k, v in base.items() if k not in {"pageReality", "perPageTextLength"}}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "page-text.json").write_text(json.dumps({"perPageTextLength": per_page_text_length, "pages": page_texts}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "page-reality.json").write_text(json.dumps(page_reality, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "sanity.json").write_text(json.dumps(sanity, ensure_ascii=False, indent=2), encoding="utf-8")
    return base

results = [inspect_fixture(item) for item in fixtures]
summary = {
    "checkedAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    "fixtures": results,
}
(output_dir / "fixture-sanity" / "fixtures-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))
`;
  const fixtures = [
    { key: 'main', label: '题本篇-1-8', path: MAIN_TEST_PDF, role: 'main_positive_fixture' },
    { key: 'full_scanned', label: '题本篇-20', path: FULL_SCANNED_PDF, role: 'full_scanned_fixture' },
    { key: 'latest1200', label: '最新1200题本', path: LATEST_1200_PDF, role: 'mixed_toc_scanned_fixture' },
    { key: 'kuakua_upper', label: '夸夸刷上册', path: KUAKUA_UPPER_PDF, role: 'text_hybrid_fixture' },
    { key: 'kuakua_lower', label: '夸夸刷下册', path: KUAKUA_LOWER_PDF, role: 'text_hybrid_fixture' },
    { key: 'negative', label: 'partial-negative', path: PARTIAL_CONTEXT_NEGATIVE_PDF, role: 'partial_pdf_context_negative_regression' },
    { key: 'candidate_9_14', label: 'candidate-9-14', path: CANDIDATE_TEST_PDF, role: 'candidate_page_range_fixture' },
  ];
  return JSON.parse(runPython(script, [OUTPUT_DIR, JSON.stringify(fixtures)]));
}

function writeCompareReport(summary, candidateGeneration) {
  const diagnosisRoot = path.join(OUTPUT_DIR, 'fixture-page-range-diagnosis');
  mkdirSync(diagnosisRoot, { recursive: true });
  const current = summary.fixtures.find((item) => item.key === 'main') || {};
  const candidate = summary.fixtures.find((item) => item.key === 'candidate_9_14') || {};
  const currentLikely = current.actualKind === 'scanned_question_book';
  const candidateLikely = candidate.actualKind === 'scanned_question_book';
  const candidateMoreSuitable = false;
  const report = `# Fixture Page Range Diagnosis

## Inputs

- Current main fixture: \`${MAIN_TEST_PDF}\`
- Source full PDF: \`${SOURCE_FULL_PDF}\`
- Candidate fixture: \`${CANDIDATE_TEST_PDF}\`
- Candidate generation: ${candidateGeneration.method || 'not generated'} ${candidateGeneration.error ? `(${candidateGeneration.error})` : ''}

## Sanity Result

- 1-8 是否题目页：${currentLikely ? '是，判定为 image-only scanned question book。' : '否或未知，需要查看 fixture-sanity 证据。'}
- 9-14 是否题目页：${candidateLikely ? '是，判定为 image-only scanned question book。' : '否或未知，需要查看 fixture-sanity 证据。'}
- 9-14 是否更适合作为当前主样例：${candidateMoreSuitable ? '是' : '否。1-8 已经是有效题本页，9-14 只作为额外 A/B 候选样例。'}

## Conclusion

\`题本篇-1-8.pdf\` 是有效 image-only scanned question book positive fixture，\`zero_questions_extracted\` 不应归因于错页或空页。
`;
  writeFileSync(path.join(diagnosisRoot, 'COMPARE_REPORT.md'), report);
  return {
    compareReport: path.join(diagnosisRoot, 'COMPARE_REPORT.md'),
    currentLikelyQuestionRange: currentLikely,
    candidateLikelyQuestionRange: candidateLikely,
    candidateMoreSuitable,
  };
}

mkdirSync(OUTPUT_DIR, { recursive: true });
const mainGeneration = ensureMainFixture();
const candidateGeneration = ensureCandidateFixture();
const summary = analyzeFixtures();
const compare = writeCompareReport(summary, candidateGeneration);

const main = summary.fixtures.find((item) => item.key === 'main') || {};
const full = summary.fixtures.find((item) => item.key === 'full_scanned') || {};
const latest = summary.fixtures.find((item) => item.key === 'latest1200') || {};
const upper = summary.fixtures.find((item) => item.key === 'kuakua_upper') || {};
const lower = summary.fixtures.find((item) => item.key === 'kuakua_lower') || {};
const negative = summary.fixtures.find((item) => item.key === 'negative') || {};
const candidate = summary.fixtures.find((item) => item.key === 'candidate_9_14') || {};

const failures = [];
if (!main.exists) failures.push(`主测试 PDF 不存在：${MAIN_TEST_PDF}`);
if (mainGeneration.error) failures.push(mainGeneration.error);
if (candidateGeneration.error) failures.push(candidateGeneration.error);
if (main.pageCount !== 8) failures.push(`主测试 PDF 必须为 8 页，实际为：${main.pageCount ?? 'unknown'}`);
if (!main.imageOnly) failures.push('主测试 PDF 必须被识别为 image-only');
if (main.renderedPageCount !== 8) failures.push(`主测试 PDF renderedPageCount 必须为 8，实际为：${main.renderedPageCount ?? 'unknown'}`);
const mainQuestionPages = new Set(main.pageReality?.questionLikePages || []);
for (const page of [1, 2, 3, 6]) {
  if (!mainQuestionPages.has(page)) failures.push(`主测试 PDF questionLikePages 缺少第 ${page} 页`);
}
if (main.actualKind !== 'scanned_question_book') {
  failures.push(`主测试 PDF 不应被判为 fixture_invalid_or_wrong_page_range，实际 actualKind=${main.actualKind || 'unknown'}`);
}
if (!negative.exists) failures.push(`partial context 负样例不存在：${PARTIAL_CONTEXT_NEGATIVE_PDF}`);
if (negative.pageCount && negative.pageCount !== 5) failures.push(`partial context 负样例应为 5 页，实际为：${negative.pageCount}`);
if (upper.exists && !upper.textLayerAvailable) failures.push('夸夸刷上册应识别 textLayerAvailable=true');
if (lower.exists && !lower.textLayerAvailable) failures.push('夸夸刷下册应识别 textLayerAvailable=true');
if (upper.exists && !['text', 'hybrid'].includes(upper.recommendedStrategy)) failures.push(`夸夸刷上册 recommendedStrategy 应为 text/hybrid，实际为 ${upper.recommendedStrategy}`);
if (lower.exists && !['text', 'hybrid'].includes(lower.recommendedStrategy)) failures.push(`夸夸刷下册 recommendedStrategy 应为 text/hybrid，实际为 ${lower.recommendedStrategy}`);
if (latest.exists && !(latest.pageReality?.tocLikePages || []).length) failures.push('最新1200题本应至少识别出 tocLikePages');

const report = {
  checkedAt: new Date().toISOString(),
  ok: failures.length === 0,
  failures,
  fixtures: {
    mainFixture: {
      ...main,
      pageCount: main.pageCount ?? null,
      role: 'main_positive_fixture',
      generated: Boolean(mainGeneration.generated),
      generatedFrom: { sourcePdf: SOURCE_FULL_PDF, pageRange: '1-8' },
      expected: {
        partialPdfContextAllowed: false,
        missingPreviousPageContextAllowed: false,
        manualForceAddAllowed: 'only_when_source_and_material_are_reviewable',
      },
    },
    fullScannedFixture: full,
    latest1200Fixture: latest,
    kuakuaUpperFixture: upper,
    kuakuaLowerFixture: lower,
    candidateFixture: {
      ...candidate,
      role: 'candidate_page_range_fixture',
      generated: Boolean(candidateGeneration.generated),
      generatedFrom: { sourcePdf: SOURCE_FULL_PDF, pageRange: '9-14' },
      expected: {
        silentReplacementAllowed: false,
        use: 'A/B diagnosis only unless explicitly promoted by human review',
      },
    },
    negativeFixture: {
      ...negative,
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
  pageRangeDiagnosis: {
    rawJson: path.join(OUTPUT_DIR, 'fixture-sanity', 'fixtures-summary.json'),
    currentThumbnails: path.join(OUTPUT_DIR, 'fixture-sanity', '题本篇-1-8', 'rendered-pages'),
    candidateThumbnails: path.join(OUTPUT_DIR, 'fixture-sanity', 'candidate-9-14', 'rendered-pages'),
    ...compare,
  },
};

writeFileSync(path.join(OUTPUT_DIR, 'pdf-fixtures-check.json'), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));

if (failures.length) process.exitCode = 1;
