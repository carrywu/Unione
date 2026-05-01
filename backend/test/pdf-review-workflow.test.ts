import * as assert from 'node:assert/strict';
import { mkdir, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import axios from 'axios';
import { BankStatus } from '../src/modules/bank/entities/question-bank.entity';
import { ParseTaskStatus } from '../src/modules/pdf/entities/parse-task.entity';
import { PdfService } from '../src/modules/pdf/pdf.service';
import {
  Question,
  QuestionStatus,
  QuestionType,
} from '../src/modules/question/entities/question.entity';
import { QuestionAiAction } from '../src/modules/question/entities/question-ai-action-log.entity';
import {
  MergeQuestionImagesDto,
  QuestionImageInsertPosition,
  QuestionImageRole,
} from '../src/modules/question/dto/question-review.dto';
import { QuestionService } from '../src/modules/question/question.service';

type Row = Record<string, any> & { id: string; deleted_at?: Date };

function matchesWhere(row: Row, where: Record<string, any> = {}) {
  return Object.entries(where).every(([key, value]) => row[key] === value);
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function bboxIntersects(left: number[] | null | undefined, right: number[] | null | undefined) {
  if (!left || !right) return false;
  return Math.max(left[0], right[0]) < Math.min(left[2], right[2])
    && Math.max(left[1], right[1]) < Math.min(left[3], right[3]);
}

function createRepository<T extends Row>(rows: T[]) {
  return {
    create(payload: Partial<T>) {
      return payload as T;
    },
    async findOne(options: { where: Record<string, any>; order?: Record<string, 'ASC' | 'DESC'> }) {
      let found = rows.filter((row) => !row.deleted_at && matchesWhere(row, options.where));
      if (options.order) {
        const [field, direction] = Object.entries(options.order)[0];
        found = found.sort((a, b) => {
          if (a[field] === b[field]) return 0;
          const result = a[field] > b[field] ? 1 : -1;
          return direction === 'DESC' ? -result : result;
        });
      }
      return found[0] ? clone(found[0]) : null;
    },
    async find(options: { where?: Record<string, any>; order?: Record<string, 'ASC' | 'DESC'>; take?: number } = {}) {
      let found = rows.filter((row) => !row.deleted_at && matchesWhere(row, options.where));
      if (options.order) {
        const [field, direction] = Object.entries(options.order)[0];
        found = found.sort((a, b) => {
          if (a[field] === b[field]) return 0;
          const result = a[field] > b[field] ? 1 : -1;
          return direction === 'DESC' ? -result : result;
        });
      }
      if (options.take != null) found = found.slice(0, options.take);
      return clone(found);
    },
    async count(options: { where?: Record<string, any> } = {}) {
      return rows.filter((row) => !row.deleted_at && matchesWhere(row, options.where)).length;
    },
    async update(criteria: string | Record<string, any>, patch: Partial<T>) {
      for (const row of rows) {
        const matched = typeof criteria === 'string' ? row.id === criteria : matchesWhere(row, criteria);
        if (matched) Object.assign(row, patch);
      }
    },
    async save(entity: T) {
      const index = rows.findIndex((row) => row.id === entity.id);
      if (index >= 0) {
        rows[index] = { ...rows[index], ...clone(entity) };
        return clone(rows[index]);
      }
      rows.push(clone(entity));
      return clone(entity);
    },
    async softRemove(entity: T) {
      const row = rows.find((item) => item.id === entity.id);
      if (row) row.deleted_at = new Date();
    },
  };
}

function harness() {
  const now = new Date('2026-04-29T10:00:00.000Z');
  const banks = [
    {
      id: 'bank-1',
      status: BankStatus.Draft,
      total_count: 0,
      created_at: now,
    },
  ];
  const tasks = [
    {
      id: 'task-1',
      bank_id: 'bank-1',
      file_url: 'https://example.test/book.pdf',
      file_name: 'book.pdf',
      status: ParseTaskStatus.Done,
      progress: 100,
      total_count: 3,
      done_count: 3,
      attempt: 0,
      created_at: now,
    },
  ];
  const questions = [
    {
      id: 'q1',
      bank_id: 'bank-1',
      parse_task_id: 'task-1',
      index_num: 1,
      type: QuestionType.Single,
      content: '高置信题',
      option_a: 'A',
      option_b: 'B',
      option_c: 'C',
      option_d: 'D',
      images: [{ url: '1.png', role: 'chart', image_order: 1 }],
      status: QuestionStatus.Draft,
      needs_review: false,
      parse_confidence: 0.92,
      parse_warnings: [],
      answer: 'A',
      analysis: '旧官方解析',
      ai_candidate_answer: 'C',
      ai_candidate_analysis: 'AI 候选解析',
      ai_answer_confidence: 0.86,
      ai_solver_provider: 'bailian-deepseek',
      ai_solver_model: 'deepseek-r1',
      ai_solver_first_model: 'fast-model',
      ai_solver_final_model: 'pro-model',
      ai_solver_rechecked: true,
      created_at: now,
    },
    {
      id: 'q2',
      bank_id: 'bank-1',
      parse_task_id: 'task-1',
      index_num: 2,
      type: QuestionType.Single,
      content: '低置信题',
      option_a: 'A',
      option_b: 'B',
      option_c: 'C',
      option_d: 'D',
      images: [{ url: '2.png', role: 'table', image_order: 1 }],
      status: QuestionStatus.Draft,
      needs_review: true,
      parse_confidence: 0.44,
      parse_warnings: ['visual_assignment_low_confidence'],
      created_at: now,
    },
    {
      id: 'q3',
      bank_id: 'bank-1',
      parse_task_id: 'task-1',
      index_num: 3,
      type: QuestionType.Single,
      content: '下一题',
      option_a: 'A',
      option_b: 'B',
      option_c: 'C',
      option_d: 'D',
      images: [],
      status: QuestionStatus.Draft,
      needs_review: false,
      parse_confidence: 0.9,
      parse_warnings: [],
      created_at: now,
    },
  ] as Question[];
  const materials: Row[] = [];
  const aiActionLogs: Row[] = [];
  const configs: Row[] = [];
  const taskRepository = createRepository(tasks as Row[]);
  const questionRepository = createRepository(questions as unknown as Row[]);
  const aiActionLogRepository = createRepository(aiActionLogs);
  const materialRepository = createRepository(materials);
  const bankRepository = createRepository(banks as Row[]);
  const configRepository = createRepository(configs);
  const configService = { get: (_key: string, fallback?: string) => fallback } as any;
  const uploadService = {
    uploadBuffer: async () => ({ url: 'manual.png' }),
  };

  return {
    banks,
    questions,
    aiActionLogs,
    configs,
    pdfService: new PdfService(
      taskRepository as any,
      questionRepository as any,
      materialRepository as any,
      bankRepository as any,
      configRepository as any,
      configService,
      uploadService as any,
    ),
    questionService: new QuestionService(
      questionRepository as any,
      aiActionLogRepository as any,
      createRepository([]) as any,
      materialRepository as any,
      bankRepository as any,
      taskRepository as any,
      configRepository as any,
      configService,
    ),
  };
}

async function run() {
  await testPublishSkipsLowConfidenceAndWarningQuestions();
  await testReadabilityReviewSendsSourceBboxSeparatelyFromImages();
  await testReadabilityReviewKeepsAdjacentSourceAndVisualLayersSeparated();
  await testQuestionImageOperationsOnlyTouchCurrentQuestion();
  await testMergeAdjacentQuestionImagesMarksSharedGroup();
  await testAiRepairReturnsProposalWithoutPersisting();
  await testPaperCandidatesDraftAndPreviewFromAiPreauditArtifacts();
  await testPaperCandidatesRejectManualForceAddWhenSourceTextSpanMissing();
  await testPaperDraftRejectsForgedManualForceAddWithoutSourceEvidence();
  await testPdfSavePersistsVisionAiCorrectionFields();
  await testPdfSavePersistsAiSolverCandidateFields();
  await testPdfSavePersistsAiPreauditFields();
  await testAcceptAiAnswerRecordsAuditLog();
  await testAcceptAiAnalysisRecordsAuditLog();
  await testAcceptAiBothRecordsAuditLog();
  await testIgnoreAiSuggestionRecordsAuditLog();
}

async function testPublishSkipsLowConfidenceAndWarningQuestions() {
  const h = harness();

  const result = await h.pdfService.publishResult('task-1', { publish_bank: true });

  assert.equal(result.published_count, 2);
  assert.equal(result.review_count, 1);
  assert.equal(h.questions[0].status, QuestionStatus.Published);
  assert.equal(h.questions[1].status, QuestionStatus.Draft);
  assert.equal(h.questions[1].needs_review, true);
  assert.deepEqual(h.questions[1].parse_warnings, ['visual_assignment_low_confidence']);
}

async function testReadabilityReviewSendsSourceBboxSeparatelyFromImages() {
  const h = harness();
  Object.assign(h.questions[0], {
    page_num: 1,
    page_range: [1],
    source_page_start: 1,
    source_page_end: 1,
    source_bbox: [65, 378, 476, 494],
    source_anchor_text: '【例 1】',
    image_refs: ['p1-img1'],
    visual_refs: [{ id: 'p1-img1', page: 1, bbox: [108, 197, 434, 351] }],
  });
  let requestBody: any = null;
  const originalPost = axios.post;
  (axios as any).post = async (_url: string, body: any) => {
    requestBody = body;
    return {
      data: {
        readable: true,
        needs_review: false,
        score: 0.91,
        reasons: [],
        prompts: [],
        focus_areas: [],
        source: 'test',
      },
    };
  };
  try {
    await h.questionService.reviewReadability('q1');
  } finally {
    (axios as any).post = originalPost;
  }

  assert.deepEqual(requestBody.source.source_bbox, [65, 378, 476, 494]);
  assert.equal(requestBody.source.source_page_start, 1);
  assert.deepEqual(requestBody.question.image_refs, ['p1-img1']);
  assert.deepEqual(requestBody.question.visual_refs, [{ id: 'p1-img1', page: 1, bbox: [108, 197, 434, 351] }]);
  assert.deepEqual(requestBody.question.images, h.questions[0].images);
  assert.equal(requestBody.question.source_bbox, undefined);
}

async function testReadabilityReviewKeepsAdjacentSourceAndVisualLayersSeparated() {
  const h = harness();
  Object.assign(h.questions[0], {
    page_num: 1,
    source_page_start: 1,
    source_page_end: 1,
    source_bbox: [65, 378, 476, 494],
    images: [{ ref: 'p1-img1', bbox: [108, 197, 434, 351] }],
    image_refs: ['p1-img1'],
    visual_refs: [{ id: 'p1-img1', page: 1, bbox: [108, 197, 434, 351] }],
  });
  Object.assign(h.questions[1], {
    page_num: 1,
    source_page_start: 1,
    source_page_end: 2,
    source_bbox: [65, 646, 476, 678],
    images: [{ ref: 'p1-img2', bbox: [143, 503, 398, 619] }],
    image_refs: ['p1-img2'],
    visual_refs: [{ id: 'p1-img2', page: 1, bbox: [143, 503, 398, 619] }],
  });
  const requestBodies: any[] = [];
  const originalPost = axios.post;
  (axios as any).post = async (_url: string, body: any) => {
    requestBodies.push(body);
    return {
      data: {
        readable: true,
        needs_review: false,
        score: 0.91,
        reasons: [],
        prompts: [],
        focus_areas: [],
        source: 'test',
      },
    };
  };
  try {
    await h.questionService.reviewReadability('q1');
    await h.questionService.reviewReadability('q2');
  } finally {
    (axios as any).post = originalPost;
  }

  assert.equal(requestBodies.length, 2);
  assert.deepEqual(requestBodies[0].source.source_bbox, [65, 378, 476, 494]);
  assert.deepEqual(requestBodies[0].question.visual_refs.map((item: any) => item.id), ['p1-img1']);
  assert.deepEqual(requestBodies[0].question.images.map((item: any) => item.ref), ['p1-img1']);
  assert.deepEqual(requestBodies[1].source.source_bbox, [65, 646, 476, 678]);
  assert.deepEqual(requestBodies[1].question.visual_refs.map((item: any) => item.id), ['p1-img2']);
  assert.deepEqual(requestBodies[1].question.images.map((item: any) => item.ref), ['p1-img2']);
  assert.equal(requestBodies[0].question.source_bbox, undefined);
  assert.equal(requestBodies[1].question.source_bbox, undefined);
  assert.equal(bboxIntersects(requestBodies[0].source.source_bbox, requestBodies[1].question.visual_refs[0].bbox), false);
  assert.equal(bboxIntersects(requestBodies[1].source.source_bbox, requestBodies[0].source.source_bbox), false);
}

async function testQuestionImageOperationsOnlyTouchCurrentQuestion() {
  const h = harness();

  await h.questionService.addQuestionImage('q1', {
    url: 'new.png',
    image_role: QuestionImageRole.QuestionVisual,
    insert_position: QuestionImageInsertPosition.BelowStem,
  });
  await h.questionService.reorderQuestionImages('q1', ['new.png', '1.png']);
  await h.questionService.deleteQuestionImage('q1', '1.png');
  await h.questionService.moveQuestionImage('q1', { image_url: 'new.png', direction: 'next' });

  assert.deepEqual((h.questions[0].images as any[]).map((image) => image.url), []);
  assert.deepEqual((h.questions[1].images as any[]).map((image) => image.url), ['2.png', 'new.png']);
  assert.equal((h.questions[1].images as any[])[1].image_order, 2);
  assert.deepEqual((h.questions[2].images as any[]), []);
}

async function testMergeAdjacentQuestionImagesMarksSharedGroup() {
  const h = harness();
  await h.questionService.addQuestionImage('q1', {
    url: 'new.png',
    image_role: QuestionImageRole.QuestionVisual,
    insert_position: QuestionImageInsertPosition.BelowStem,
  });

  const result = await h.questionService.mergeQuestionImages('q1', {
    image_url: '1.png',
    next_image_url: 'new.png',
  } as MergeQuestionImagesDto);

  const images = result.images as any[];
  assert.equal(images.length, 2);
  assert.equal(images[0].same_visual_group_id, images[1].same_visual_group_id);
  assert.equal(images[0].image_order, 1);
  assert.equal(images[1].image_order, 2);
  assert.equal(result.needs_review, true);
}

async function testAiRepairReturnsProposalWithoutPersisting() {
  const h = harness();
  const originalPost = axios.post;
  (axios as any).post = async () => ({
    data: {
      content: '修复后的题干',
      options: { A: '甲', B: '乙', C: '丙', D: '丁' },
      visual_refs: [],
      material_text: '',
      remove_texts: ['资料分析题库-夸夸刷'],
      warnings: [],
      confidence: 0.82,
    },
  });
  try {
    const proposal = await h.questionService.repairQuestionWithAi('q2');

    assert.equal(proposal.content, '修复后的题干');
    assert.equal(h.questions[1].content, '低置信题');
    assert.equal(h.questions[1].needs_review, true);
  } finally {
    (axios as any).post = originalPost;
  }
}

async function testPaperCandidatesDraftAndPreviewFromAiPreauditArtifacts() {
  const h = harness();
  const debugDir = join(process.cwd(), 'debug', 'pdf-ai-preaudit', 'task-1');
  const draftRoot = join(process.cwd(), 'debug', 'paper-drafts');
  const draftIds: string[] = [];

  await rm(debugDir, { recursive: true, force: true });
  await mkdir(debugDir, { recursive: true });

  try {
    await writeFile(
      join(debugDir, 'ai-preaudit-debug.json'),
      JSON.stringify(
        {
          qwen_vl_enabled: true,
          qwen_vl_call_count_after: 2,
          final_verdict: { total_count: 2, done_count: 2 },
        },
        null,
        2,
      ),
      'utf-8',
    );
    await writeFile(
      join(debugDir, 'final-preview-payload.json'),
      JSON.stringify(
        {
          questions: [
            {
              question_no: 1,
              stem: '完整资料分析题干',
              options: { A: '甲', B: '乙', C: '丙', D: '丁' },
              preview_image_path: 'chart.png',
              visual_assets: [{ url: 'chart.png', ref: 'p1-img1' }],
              visual_parse_status: 'success',
              source_page_refs: [1],
              source_bbox: [10, 20, 220, 90],
              source_text_span: '完整资料分析题干',
              risk_flags: [],
            },
            {
              question_no: 2,
              stem: '需要人工复核的题干',
              options: { A: '甲', B: '乙', C: '丙', D: '丁' },
              visual_parse_status: 'success',
              source_page_refs: [2],
              source_bbox: [12, 120, 230, 188],
              source_text_span: '需要人工复核的题干',
              risk_flags: [],
            },
          ],
        },
        null,
        2,
      ),
      'utf-8',
    );
    await writeFile(
      join(debugDir, 'semantic-groups.json'),
      JSON.stringify(
        [
          {
            question_no: 1,
            source_page_start: 1,
            source_page_end: 1,
            source_text_span: '完整资料分析题干',
            stem_group: {
              text: '完整资料分析题干',
              bbox: [10, 20, 220, 90],
              source_text_span: '完整资料分析题干',
            },
            options_group: {
              blocks: [
                { label: 'A', text: '甲', bbox: [10, 95, 80, 115] },
                { label: 'B', text: '乙', bbox: [90, 95, 160, 115] },
                { label: 'C', text: '丙', bbox: [10, 120, 80, 140] },
                { label: 'D', text: '丁', bbox: [90, 120, 160, 140] },
              ],
            },
            material_group: { id: 'material-1', bbox: [8, 8, 240, 180] },
            visual_group: { blocks: [{ ref: 'p1-img1', bbox: [20, 150, 180, 260] }] },
            title_group: { blocks: [{ text: '资料图', bbox: [20, 140, 180, 148] }] },
          },
          {
            question_no: 2,
            source_page_start: 2,
            source_page_end: 2,
            source_text_span: '需要人工复核的题干',
            stem_group: {
              text: '需要人工复核的题干',
              bbox: [12, 120, 230, 188],
              source_text_span: '需要人工复核的题干',
            },
            options_group: {
              blocks: [
                { label: 'A', text: '甲', bbox: [12, 195, 82, 215] },
                { label: 'B', text: '乙', bbox: [92, 195, 162, 215] },
                { label: 'C', text: '丙', bbox: [12, 220, 82, 240] },
                { label: 'D', text: '丁', bbox: [92, 220, 162, 240] },
              ],
            },
          },
        ],
        null,
        2,
      ),
      'utf-8',
    );
    await writeFile(
      join(debugDir, 'ai-audit-results.json'),
      JSON.stringify(
        [
          {
            question_no: 1,
            ai_audit_status: 'passed',
            ai_audit_verdict: '可通过',
            ai_audit_summary: '结构完整，可进入试卷草稿。',
            answer_suggestion: 'A',
            answer_confidence: 0.91,
            analysis_suggestion: '根据图表读取数据，选择 A。',
            risk_flags: [],
          },
          {
            question_no: 2,
            ai_audit_status: 'warning',
            ai_audit_summary: '结构可核验，但需要人工确认答案解析后才能入卷。',
            answer_suggestion: 'B',
            answer_confidence: 0.62,
            analysis_suggestion: '需人工核对原卷后确认。',
            risk_flags: ['need_manual_fix'],
          },
        ],
        null,
        2,
      ),
      'utf-8',
    );

    const candidates = await h.pdfService.getPaperCandidates('task-1');

    assert.equal(candidates.summary.total, 2);
    assert.equal(candidates.summary.can_add_count, 1);
    assert.equal(candidates.summary.need_manual_fix_count, 1);
    assert.equal(candidates.questions[0].can_add_to_paper, true);
    assert.equal(candidates.questions[0].cannot_add_reason, null);
    assert.equal(candidates.questions[0].manualReviewable, true);
    assert.equal(candidates.questions[0].source_locator_available, true);
    assert.deepEqual(candidates.questions[0].source_bbox, [10, 20, 220, 90]);
    assert.equal(candidates.questions[0].source_text_span, '完整资料分析题干');
    assert.equal(candidates.questions[1].can_add_to_paper, false);
    assert.equal(candidates.questions[1].manualReviewable, true);
    assert.equal(candidates.questions[1].manualForceAddAllowed, true);
    assert.equal(candidates.questions[1].source_locator_available, true);
    assert.match(candidates.questions[1].cannot_add_reason, /AI 预审核 warning/);

    const autoDraft = await h.pdfService.createDraftPaper({
      source_task_id: 'task-1',
      title: '自动草稿',
    });
    draftIds.push(autoDraft.paper_id);
    assert.equal(autoDraft.questions.length, 1);
    assert.equal(autoDraft.score, 1);

    const forcedDraft = await h.pdfService.createDraftPaper({
      source_task_id: 'task-1',
      title: '人工强制草稿',
      questions: candidates.questions,
    });
    draftIds.push(forcedDraft.paper_id);
    assert.equal(forcedDraft.questions.length, 2);
    assert.equal(forcedDraft.score, 2);

    const preview = await h.pdfService.previewDraftPaper(forcedDraft.paper_id);
    assert.equal(preview.preview.question_count, 2);
    assert.equal(preview.preview.total_score, 2);
  } finally {
    await rm(debugDir, { recursive: true, force: true });
    await Promise.all(
      draftIds.map((paperId) =>
        rm(join(draftRoot, `${paperId}.json`), { force: true }),
      ),
    );
  }
}

async function testPaperCandidatesRejectManualForceAddWhenSourceTextSpanMissing() {
  const h = harness();
  const debugDir = join(process.cwd(), 'debug', 'pdf-ai-preaudit', 'task-1');
  const draftRoot = join(process.cwd(), 'debug', 'paper-drafts');

  await rm(debugDir, { recursive: true, force: true });
  await rm(draftRoot, { recursive: true, force: true });
  await mkdir(debugDir, { recursive: true });

  try {
    await writeFile(
      join(debugDir, 'ai-preaudit-debug.json'),
      JSON.stringify({ qwen_vl_enabled: true, qwen_vl_call_count_after: 1 }, null, 2),
      'utf-8',
    );
    await writeFile(
      join(debugDir, 'final-preview-payload.json'),
      JSON.stringify(
        {
          questions: [
            {
              question_no: 1,
              stem: '普通常识题干',
              options: { A: '甲', B: '乙', C: '丙', D: '丁' },
              visual_parse_status: 'success',
              source_page_refs: [1],
              source_bbox: [10, 20, 220, 90],
              risk_flags: [],
            },
          ],
        },
        null,
        2,
      ),
      'utf-8',
    );
    await writeFile(
      join(debugDir, 'ai-audit-results.json'),
      JSON.stringify(
        [
          {
            question_no: 1,
            ai_audit_status: 'warning',
            ai_audit_summary: 'source bbox 存在，但缺少 source_text_span，不能强制入卷。',
            answer_suggestion: 'A',
            analysis_suggestion: '解析待人工核验。',
            risk_flags: [],
          },
        ],
        null,
        2,
      ),
      'utf-8',
    );

    const candidates = await h.pdfService.getPaperCandidates('task-1');
    assert.equal(candidates.questions.length, 1);
    assert.equal(candidates.questions[0].source_locator_available, true);
    assert.deepEqual(candidates.questions[0].source_page_refs, [1]);
    assert.deepEqual(candidates.questions[0].source_bbox, [10, 20, 220, 90]);
    assert.equal(candidates.questions[0].source_text_span, null);
    assert.equal(candidates.questions[0].manualReviewable, false);
    assert.equal(candidates.questions[0].manualForceAddAllowed, false);
    assert.match(candidates.questions[0].cannot_add_reason, /source_text_span|source evidence|无法人工核验/);
  } finally {
    await rm(debugDir, { recursive: true, force: true });
    await rm(draftRoot, { recursive: true, force: true });
  }
}

async function testPaperDraftRejectsForgedManualForceAddWithoutSourceEvidence() {
  const h = harness();
  const debugDir = join(process.cwd(), 'debug', 'pdf-ai-preaudit', 'task-1');
  const draftRoot = join(process.cwd(), 'debug', 'paper-drafts');

  await rm(debugDir, { recursive: true, force: true });
  await rm(draftRoot, { recursive: true, force: true });
  await mkdir(debugDir, { recursive: true });

  try {
    await writeFile(
      join(debugDir, 'ai-preaudit-debug.json'),
      JSON.stringify({ qwen_vl_enabled: true, qwen_vl_call_count_after: 1 }, null, 2),
      'utf-8',
    );
    await writeFile(
      join(debugDir, 'final-preview-payload.json'),
      JSON.stringify(
        {
          questions: [
            {
              question_no: 1,
              stem: '缺少 source evidence 的题干',
              options: { A: '甲', B: '乙', C: '丙', D: '丁' },
              visual_parse_status: 'success',
              source_page_refs: [],
              risk_flags: [],
            },
          ],
        },
        null,
        2,
      ),
      'utf-8',
    );
    await writeFile(
      join(debugDir, 'ai-audit-results.json'),
      JSON.stringify(
        [
          {
            question_no: 1,
            ai_audit_status: 'warning',
            ai_audit_summary: '需要人工核验，但 source evidence 缺失。',
            answer_suggestion: 'A',
            analysis_suggestion: '解析待人工核验。',
            risk_flags: [],
          },
        ],
        null,
        2,
      ),
      'utf-8',
    );

    const candidates = await h.pdfService.getPaperCandidates('task-1');
    assert.equal(candidates.questions.length, 1);
    assert.equal(candidates.questions[0].manualReviewable, false);
    assert.equal(candidates.questions[0].manualForceAddAllowed, false);

    const forgedCandidate = {
      ...candidates.questions[0],
      can_add_to_paper: true,
      manualReviewable: true,
      manualForceAddAllowed: true,
      source_locator_available: true,
      source_page_refs: [1],
    };

    await assert.rejects(
      () =>
        h.pdfService.createDraftPaper({
          source_task_id: 'task-1',
          title: '伪造人工强制草稿',
          questions: [forgedCandidate],
        }),
      /不可入卷|无法人工核验|source evidence|候选题/,
    );

    const emptyDraft = await h.pdfService.createDraftPaper({
      source_task_id: 'task-1',
      title: '空草稿',
    });
    assert.equal(emptyDraft.questions.length, 0);
    await assert.rejects(
      () =>
        h.pdfService.updateDraftPaper(emptyDraft.paper_id, {
          questions: [forgedCandidate],
        }),
      /不可入卷|无法人工核验|source evidence|候选题/,
    );
  } finally {
    await rm(debugDir, { recursive: true, force: true });
    await rm(draftRoot, { recursive: true, force: true });
  }
}

async function testPdfSavePersistsVisionAiCorrectionFields() {
  const h = harness();
  await (h.pdfService as any).saveQuestions(
    'task-1',
    'bank-1',
    [
      {
        index: 4,
        type: 'single',
        content: 'AI 纠偏题',
        options: { A: '甲', B: '乙', C: '丙', D: '丁' },
        images: [],
        visual_refs: [{ id: 'p3-img1', page: 3 }],
        image_refs: ['p3-img1'],
        ai_corrections: [
          {
            provider: 'qwen-vl',
            confidence: 0.92,
            action: 'update_visual_refs',
            reason: '表格标题和主体属于该题',
            status: 'applied',
          },
        ],
        ai_confidence: 0.92,
        ai_provider: 'qwen-vl',
        ai_review_notes: '视觉模型认为该文化产业表格应归属第6题',
      },
    ],
    new Map(),
  );

  const saved = h.questions.find((question) => question.index_num === 4) as any;
  assert.equal(saved.ai_provider, 'qwen-vl');
  assert.equal(saved.ai_confidence, 0.92);
  assert.equal(saved.ai_review_notes, '视觉模型认为该文化产业表格应归属第6题');
  assert.equal(saved.ai_corrections[0].status, 'applied');
}

async function testPdfSavePersistsAiSolverCandidateFields() {
  const h = harness();
  await (h.pdfService as any).saveQuestions(
    'task-1',
    'bank-1',
    [
      {
        index: 5,
        type: 'single',
        content: 'AI 候选答案题',
        options: { A: '甲', B: '乙', C: '丙', D: '丁' },
        answer: 'A',
        analysis: '官方解析',
        ai_candidate_answer: 'C',
        ai_candidate_analysis: 'AI 候选解析',
        ai_answer_confidence: 0.86,
        ai_reasoning_summary: '资料分析表格读取',
        ai_knowledge_points: ['资料分析', '表格读取'],
        ai_risk_flags: ['requires_table'],
        ai_solver_provider: 'bailian-deepseek',
        ai_solver_model: 'deepseek-r1',
        ai_solver_first_model: 'fast-model',
        ai_solver_final_model: 'pro-model',
        ai_solver_rechecked: true,
        ai_solver_recheck_reason: 'low_confidence',
        ai_solver_recheck_result: {
          previous_result: { ai_candidate_answer: 'B' },
          pro_result: { ai_candidate_answer: 'C' },
          selected_result: 'pro',
        },
        ai_solver_created_at: '2026-04-30T10:00:00.000Z',
        ai_answer_conflict: true,
        needs_review: true,
        parse_warnings: ['ai_answer_conflict'],
      },
    ],
    new Map(),
  );

  const saved = h.questions.find((question) => question.index_num === 5) as any;
  assert.equal(saved.answer, 'A');
  assert.equal(saved.analysis, '官方解析');
  assert.equal(saved.ai_candidate_answer, 'C');
  assert.equal(saved.ai_candidate_analysis, 'AI 候选解析');
  assert.equal(saved.ai_answer_confidence, 0.86);
  assert.deepEqual(saved.ai_knowledge_points, ['资料分析', '表格读取']);
  assert.deepEqual(saved.ai_risk_flags, ['requires_table']);
  assert.equal(saved.ai_solver_provider, 'bailian-deepseek');
  assert.equal(saved.ai_solver_model, 'deepseek-r1');
  assert.equal(saved.ai_solver_first_model, 'fast-model');
  assert.equal(saved.ai_solver_final_model, 'pro-model');
  assert.equal(saved.ai_solver_rechecked, true);
  assert.equal(saved.ai_solver_recheck_reason, 'low_confidence');
  assert.equal(saved.ai_solver_recheck_result.selected_result, 'pro');
  assert.equal(saved.ai_answer_conflict, true);
  assert.equal(saved.needs_review, true);
}

async function testPdfSavePersistsAiPreauditFields() {
  const h = harness();
  await (h.pdfService as any).saveQuestions(
    'task-1',
    'bank-1',
    [
      {
        index: 6,
        type: 'single',
        content: '2017～2021 五年间重庆市城镇常住居民人均可支配收入与农村常住居民人均可支配收入之比最小的是：',
        options: { A: '2017 年', B: '2018 年', C: '2020 年', D: '2021 年' },
        images: [
          {
            url: 'chart.png',
            ref: 'p5-img1',
            image_role: 'chart',
            belongs_to_question: true,
            linked_question_no: 6,
            linked_by: 'ai',
            link_reason: '图表标题和题干均指向重庆居民收入。',
            visual_summary: '2017～2021年重庆市城镇与农村常住居民收入柱状图。',
            visual_parse_status: 'success',
            visual_confidence: 0.82,
          },
        ],
        has_visual_context: true,
        visual_parse_status: 'success',
        visual_summary: '2017～2021年重庆市城镇与农村常住居民收入柱状图。',
        visual_confidence: 0.82,
        ai_candidate_answer: 'D',
        ai_candidate_analysis: '逐年计算城镇/农村收入比，2021年最小，故选D。',
        ai_answer_confidence: 0.76,
        ai_audit_status: 'warning',
        ai_audit_verdict: '需复核',
        ai_audit_summary: 'AI 能理解题目和图表，但关键数值建议人工复核。',
        ai_can_understand_question: true,
        ai_can_solve_question: true,
        ai_reviewed_before_human: true,
        question_quality: {
          stem_complete: true,
          options_complete: true,
          visual_context_complete: true,
          answer_derivable: true,
          analysis_derivable: true,
          duplicate_suspected: false,
          needs_review: true,
          review_reasons: ['关键数值需人工复核'],
        },
        ai_risk_flags: ['图表数据识别不完整，建议人工复核'],
        needs_review: true,
      },
    ],
    new Map(),
  );

  const saved = h.questions.find((question) => question.index_num === 6) as any;
  assert.equal(saved.visual_parse_status, 'success');
  assert.equal(saved.has_visual_context, true);
  assert.equal(saved.ai_audit_status, 'warning');
  assert.equal(saved.ai_audit_verdict, '需复核');
  assert.equal(saved.ai_reviewed_before_human, true);
  assert.equal(saved.ai_can_understand_question, true);
  assert.equal(saved.ai_can_solve_question, true);
  assert.equal(saved.images[0].belongs_to_question, true);
  assert.equal(saved.images[0].linked_by, 'ai');
  assert.equal(saved.question_quality.stem_complete, true);
  assert.deepEqual(saved.ai_risk_flags, ['图表数据识别不完整，建议人工复核']);
}

async function testAcceptAiAnswerRecordsAuditLog() {
  const h = harness();

  await h.questionService.applyAiAction('q1', { action: QuestionAiAction.AcceptAnswer }, 'admin-1');

  assert.equal(h.questions[0].answer, 'C');
  assert.equal(h.questions[0].analysis, '旧官方解析');
  assert.equal(h.aiActionLogs.length, 1);
  assert.equal(h.aiActionLogs[0].action, QuestionAiAction.AcceptAnswer);
  assert.equal(h.aiActionLogs[0].field, 'answer');
  assert.equal(h.aiActionLogs[0].old_value, 'A');
  assert.equal(h.aiActionLogs[0].new_value, 'C');
  assert.equal(h.aiActionLogs[0].operator_id, 'admin-1');
  assert.equal(h.aiActionLogs[0].ai_solver_final_model, 'pro-model');
}

async function testAcceptAiAnalysisRecordsAuditLog() {
  const h = harness();

  await h.questionService.applyAiAction('q1', { action: QuestionAiAction.AcceptAnalysis }, 'admin-1');

  assert.equal(h.questions[0].answer, 'A');
  assert.equal(h.questions[0].analysis, 'AI 候选解析');
  assert.equal(h.aiActionLogs.length, 1);
  assert.equal(h.aiActionLogs[0].action, QuestionAiAction.AcceptAnalysis);
  assert.equal(h.aiActionLogs[0].field, 'analysis');
  assert.equal(h.aiActionLogs[0].old_value, '旧官方解析');
  assert.equal(h.aiActionLogs[0].new_value, 'AI 候选解析');
}

async function testAcceptAiBothRecordsAuditLog() {
  const h = harness();

  await h.questionService.applyAiAction('q1', { action: QuestionAiAction.AcceptBoth }, 'admin-1');

  assert.equal(h.questions[0].answer, 'C');
  assert.equal(h.questions[0].analysis, 'AI 候选解析');
  assert.equal(h.aiActionLogs.length, 1);
  assert.equal(h.aiActionLogs[0].action, QuestionAiAction.AcceptBoth);
  assert.equal(h.aiActionLogs[0].field, 'answer,analysis');
  assert.deepEqual(JSON.parse(h.aiActionLogs[0].old_value), {
    answer: 'A',
    analysis: '旧官方解析',
  });
  assert.deepEqual(JSON.parse(h.aiActionLogs[0].new_value), {
    answer: 'C',
    analysis: 'AI 候选解析',
  });
}

async function testIgnoreAiSuggestionRecordsAuditLog() {
  const h = harness();

  const result = await h.questionService.applyAiAction('q1', { action: QuestionAiAction.IgnoreSuggestion }, 'admin-1');

  assert.equal(h.questions[0].answer, 'A');
  assert.equal(h.questions[0].analysis, '旧官方解析');
  assert.equal(h.aiActionLogs.length, 1);
  assert.equal(h.aiActionLogs[0].action, QuestionAiAction.IgnoreSuggestion);
  assert.equal(h.aiActionLogs[0].field, 'suggestion');
  assert.equal(h.aiActionLogs[0].old_value, '');
  assert.equal(h.aiActionLogs[0].new_value, '');
  assert.equal((result as any).ai_action_logs[0].action, QuestionAiAction.IgnoreSuggestion);
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
