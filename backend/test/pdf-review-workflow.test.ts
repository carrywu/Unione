import * as assert from 'node:assert/strict';
import axios from 'axios';
import { BankStatus } from '../src/modules/bank/entities/question-bank.entity';
import { ParseTaskStatus } from '../src/modules/pdf/entities/parse-task.entity';
import { PdfService } from '../src/modules/pdf/pdf.service';
import {
  Question,
  QuestionStatus,
  QuestionType,
} from '../src/modules/question/entities/question.entity';
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
    async find(options: { where?: Record<string, any>; order?: Record<string, 'ASC' | 'DESC'> } = {}) {
      return clone(rows.filter((row) => !row.deleted_at && matchesWhere(row, options.where)));
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
  const configs: Row[] = [];
  const taskRepository = createRepository(tasks as Row[]);
  const questionRepository = createRepository(questions as unknown as Row[]);
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

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
