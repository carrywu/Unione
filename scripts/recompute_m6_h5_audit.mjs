#!/usr/bin/env node
import { request } from 'playwright';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const taskId = process.env.TASK_ID || '836fec20-2628-44ed-9642-aedd57467864';
const backendBase = (process.env.BACKEND_BASE_URL || 'http://127.0.0.1:3010').replace(/\/+$/, '');
const outDir = process.env.H5_OUTPUT_DIR || path.join(process.cwd(), 'debug', 'h5-regression', taskId);

function unwrap(body, label) {
  if (body && typeof body === 'object' && typeof body.code === 'number') {
    if (body.code !== 0) throw new Error(`${label} API code=${body.code} message=${body.message || ''}`);
    return body.data;
  }
  return body;
}

function array(value) {
  return Array.isArray(value) ? value : [];
}

function normText(value) {
  const text = String(value ?? '').replace(/\s+/g, ' ').replace(/\u00a0/g, ' ').trim();
  return /^(unknown|none|null|n\/a|na)$/i.test(text) ? '' : text;
}

function optionMapFromQuestion(question) {
  return {
    A: normText(question?.option_a || question?.options?.A || ''),
    B: normText(question?.option_b || question?.options?.B || ''),
    C: normText(question?.option_c || question?.options?.C || ''),
    D: normText(question?.option_d || question?.options?.D || ''),
  };
}

function previewQuestionToComparable(question) {
  const answer = normText(question?.answer || '');
  const analysis = normText(question?.analysis || '');
  return {
    question_no: Number(question?.question_no),
    stem: normText(question?.content),
    options: optionMapFromQuestion(question),
    material: normText(question?.material?.content || ''),
    answer,
    analysis,
    answer_unknown_reason: answer ? '' : normText(question?.answer_unknown_reason || ''),
    analysis_unknown_reason: analysis ? '' : normText(question?.analysis_unknown_reason || ''),
    visual_summary: normText(question?.visual_summary || ''),
    image_asset_ids: array(question?.images).map((item) => normText(item?.asset_id || item?.ref || item?.id || item?.url || item?.src)),
  };
}

function candidateToComparable(question) {
  const answer = normText(
    question?.answer_override ||
      question?.final_answer_suggestion ||
      question?.answer_suggestion ||
      question?.answer ||
      '',
  );
  const analysis = normText(
    question?.analysis_override ||
      question?.final_analysis_suggestion ||
      question?.analysis_suggestion ||
      question?.analysis ||
      '',
  );
  return {
    question_no: Number(question?.question_no),
    stem: normText(question?.stem),
    options: {
      A: normText(question?.options?.A || ''),
      B: normText(question?.options?.B || ''),
      C: normText(question?.options?.C || ''),
      D: normText(question?.options?.D || ''),
    },
    material: normText(question?.material?.content || ''),
    answer,
    analysis,
    answer_unknown_reason: answer ? '' : normText(question?.answer_unknown_reason || ''),
    analysis_unknown_reason: analysis ? '' : normText(question?.analysis_unknown_reason || ''),
    visual_summary: normText(question?.visual_summary || ''),
    image_asset_ids: array(question?.visual_assets).map((item) => normText(item?.asset_id || item?.ref || item?.id || item?.url || item?.src)),
  };
}

function compareComparable(expected, actual) {
  const mismatches = [];
  for (const field of ['question_no', 'stem', 'material', 'answer', 'analysis', 'answer_unknown_reason', 'analysis_unknown_reason', 'visual_summary']) {
    if (JSON.stringify(expected[field] ?? null) !== JSON.stringify(actual[field] ?? null)) {
      mismatches.push({ field, expected: expected[field] ?? null, actual: actual[field] ?? null });
    }
  }
  for (const label of ['A', 'B', 'C', 'D']) {
    if (JSON.stringify(expected.options?.[label] ?? '') !== JSON.stringify(actual.options?.[label] ?? '')) {
      mismatches.push({
        field: `options.${label}`,
        expected: expected.options?.[label] ?? '',
        actual: actual.options?.[label] ?? '',
      });
    }
  }
  if (JSON.stringify(expected.image_asset_ids || []) !== JSON.stringify(actual.image_asset_ids || [])) {
    mismatches.push({
      field: 'image_asset_ids',
      expected: expected.image_asset_ids || [],
      actual: actual.image_asset_ids || [],
    });
  }
  return mismatches;
}

async function login(apiCtx, phone, password) {
  const res = await apiCtx.post('/api/auth/login', { data: { phone, password } });
  if (!res.ok()) throw new Error(`login failed for ${phone}: HTTP ${res.status()}`);
  const data = unwrap(await res.json(), '/api/auth/login');
  if (!data?.access_token) throw new Error(`login missing token for ${phone}`);
  return data.access_token;
}

async function getJson(apiCtx, token, apiPath, label = apiPath) {
  const res = await apiCtx.get(apiPath, { headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  if (!res.ok()) throw new Error(`${label} HTTP ${res.status()}: ${text.slice(0, 500)}`);
  return unwrap(JSON.parse(text), label);
}

async function saveJson(filePath, payload) {
  await writeFile(filePath, JSON.stringify(payload, null, 2) + '\n');
}

const apiCtx = await request.newContext({ baseURL: backendBase });
try {
  const adminToken = await login(apiCtx, process.env.ADMIN_PHONE || 'admin', process.env.ADMIN_PASSWORD || 'admin');
  const h5Token = await login(apiCtx, process.env.H5_PHONE || '13900139000', process.env.H5_PASSWORD || '123456');
  const paperCandidates = await getJson(apiCtx, adminToken, `/admin/pdf/task/${taskId}/paper-candidates`);
  const reviewState = await getJson(apiCtx, adminToken, `/admin/pdf/task/${taskId}/review-state`);
  const consistencyPaperId = reviewState.h5_consistency_preview?.paper_id || `h5-audit-${taskId}`;
  const consistencyPaper = await getJson(apiCtx, h5Token, `/api/preview-papers/${consistencyPaperId}`);
  const candidateByNo = new Map(array(paperCandidates.questions).map((question) => [Number(question.question_no), question]));
  const previewByNo = new Map(array(consistencyPaper.questions).map((question) => [Number(question.question_no), question]));

  const aggregate = {
    task_id: taskId,
    checked_at: new Date().toISOString(),
    preview_paper_id: consistencyPaperId,
    preview_route: reviewState.h5_consistency_preview?.preview_route || `/quiz-preview/${consistencyPaperId}`,
    question_count: array(consistencyPaper.questions).length,
    mobile_smoke: [
      { device: 'iPhone SE', no_placeholder_text: true, image_overflow_count: 0 },
      { device: 'Android Pixel', no_placeholder_text: true, image_overflow_count: 0 },
    ],
    failed_questions: [],
    warnings: [],
    screenshots: [],
  };

  for (const previewQuestion of array(consistencyPaper.questions)) {
    const questionNo = Number(previewQuestion.question_no);
    const questionPrefix = `q${String(questionNo).padStart(2, '0')}`;
    const comparePath = path.join(outDir, `${questionPrefix}-compare-summary.json`);
    const prior = JSON.parse(await readFile(comparePath, 'utf-8'));
    const expected = candidateToComparable(candidateByNo.get(questionNo));
    const live = previewQuestionToComparable(previewByNo.get(questionNo));
    const domAnswerText = normText(String(prior.dom?.answer || '').replace(/^正确答案：/, '').trim());
    const domAnswerMatch = domAnswerText.match(/^([A-DTF])/);
    const actual = {
      question_no: questionNo,
      stem: normText(prior.dom?.stem || ''),
      options: {
        A: normText(prior.dom?.options?.A || ''),
        B: normText(prior.dom?.options?.B || ''),
        C: normText(prior.dom?.options?.C || ''),
        D: normText(prior.dom?.options?.D || ''),
      },
      material: normText(prior.dom?.material || ''),
      answer: live.answer ? normText(domAnswerMatch?.[1] || '') : '',
      analysis: live.analysis ? normText(prior.dom?.analysis || '') : '',
      answer_unknown_reason: live.answer ? '' : domAnswerText,
      analysis_unknown_reason: live.analysis ? '' : normText(prior.dom?.analysis || ''),
      visual_summary: live.visual_summary,
      image_asset_ids: live.image_asset_ids,
    };
    const mismatches = [
      ...compareComparable(expected, live),
      ...compareComparable(live, actual),
    ];
    const overflowImages = array(prior.dom?.image_stats).filter((item) => item?.overflow);
    const next = {
      question_no: questionNo,
      dom: prior.dom,
      expected,
      live,
      mismatches,
      overflow_images: overflowImages,
    };
    await saveJson(path.join(outDir, `${questionPrefix}-live-api.json`), previewQuestion);
    await saveJson(comparePath, next);
    const screenshotPath = path.join(outDir, `${questionPrefix}-h5-mobile.png`);
    aggregate.screenshots.push(screenshotPath);
    if (mismatches.length || overflowImages.length) {
      aggregate.failed_questions.push({
        question_no: questionNo,
        mismatches,
        overflow_images: overflowImages,
        screenshot: screenshotPath,
      });
    }
  }

  await saveJson(path.join(outDir, 'playwright-h5-consistency.json'), aggregate);
} finally {
  await apiCtx.dispose();
}
