import * as assert from 'node:assert/strict';
import { ApiBankController } from '../src/modules/bank/bank.controller';
import { BankStatus } from '../src/modules/bank/entities/question-bank.entity';
import { BankService } from '../src/modules/bank/bank.service';
import { ParseTaskStatus } from '../src/modules/pdf/entities/parse-task.entity';
import { PdfService } from '../src/modules/pdf/pdf.service';
import {
  ApiQuestionController,
} from '../src/modules/question/question.controller';
import {
  QuestionStatus,
  QuestionType,
} from '../src/modules/question/entities/question.entity';
import { QuestionService } from '../src/modules/question/question.service';

type BankRow = {
  id: string;
  name: string;
  subject: string;
  source: string;
  year: number;
  status: BankStatus;
  total_count: number;
  created_at: Date;
  deleted_at?: Date;
};

type TaskRow = {
  id: string;
  bank_id: string;
  file_url: string;
  file_name: string;
  status: ParseTaskStatus;
  progress: number;
  total_count: number;
  done_count: number;
  attempt: number;
  created_at: Date;
};

type MaterialRow = {
  id: string;
  bank_id: string;
  parse_task_id?: string;
  content: string;
  images: unknown[];
  page_range?: number[] | null;
  created_at: Date;
  deleted_at?: Date;
};

type QuestionRow = {
  id: string;
  bank_id: string;
  material_id?: string | null;
  parse_task_id?: string;
  index_num: number;
  type: QuestionType;
  content: string;
  option_a?: string | null;
  option_b?: string | null;
  option_c?: string | null;
  option_d?: string | null;
  answer?: string | null;
  analysis?: string | null;
  images: unknown[];
  status: QuestionStatus;
  needs_review: boolean;
  page_num?: number | null;
  source_page_start?: number | null;
  source_page_end?: number | null;
  created_at: Date;
  deleted_at?: Date;
};

type Store = {
  banks: BankRow[];
  tasks: TaskRow[];
  materials: MaterialRow[];
  questions: QuestionRow[];
};

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function matchesWhere<T extends Record<string, any>>(
  row: T,
  where: Record<string, any> = {},
) {
  return Object.entries(where).every(([key, value]) => row[key] === value);
}

function sortRows<T extends Record<string, any>>(
  rows: T[],
  order?: Record<string, 'ASC' | 'DESC'>,
) {
  if (!order) return rows;
  const [field, direction] = Object.entries(order)[0];
  return [...rows].sort((left, right) => {
    if (left[field] === right[field]) return 0;
    const result = left[field] > right[field] ? 1 : -1;
    return direction === 'DESC' ? -result : result;
  });
}

function createBankQueryBuilder(store: Store) {
  let status: BankStatus | undefined;
  let subject: string | undefined;
  let keyword: string | undefined;
  let offset = 0;
  let limit = 20;

  return {
    orderBy() {
      return this;
    },
    skip(value: number) {
      offset = value;
      return this;
    },
    take(value: number) {
      limit = value;
      return this;
    },
    andWhere(sql: string, params: Record<string, any>) {
      if (sql.includes('bank.status')) status = params.status;
      if (sql.includes('bank.subject')) subject = params.subject;
      if (sql.includes('bank.name LIKE')) keyword = String(params.keyword).replace(/%/g, '');
      return this;
    },
    async getManyAndCount() {
      let rows = store.banks.filter((bank) => !bank.deleted_at);
      if (status) rows = rows.filter((bank) => bank.status === status);
      if (subject) rows = rows.filter((bank) => bank.subject === subject);
      if (keyword) rows = rows.filter((bank) => bank.name.includes(keyword as string));
      rows = sortRows(rows, { created_at: 'DESC' });
      return [clone(rows.slice(offset, offset + limit)), rows.length] as const;
    },
  };
}

function createQuestionQueryBuilder(store: Store) {
  let bankId: string | undefined;
  let taskId: string | undefined;
  let status: QuestionStatus | undefined;
  let needsReview: boolean | undefined;
  let hasImages: boolean | undefined;
  let keyword: string | undefined;
  let sortBy: keyof QuestionRow = 'index_num';
  let sortOrder: 'ASC' | 'DESC' = 'ASC';
  let offset = 0;
  let limit = 20;

  return {
    leftJoinAndMapOne() {
      return this;
    },
    skip(value: number) {
      offset = value;
      return this;
    },
    take(value: number) {
      limit = value;
      return this;
    },
    orderBy(field: string, order: 'ASC' | 'DESC') {
      sortBy = field.replace('question.', '') as keyof QuestionRow;
      sortOrder = order;
      return this;
    },
    andWhere(sql: string, params: Record<string, any>) {
      if (sql.includes('question.bank_id')) bankId = params.bankId;
      if (sql.includes('question.parse_task_id')) taskId = params.taskId;
      if (sql.includes('question.status')) status = params.status;
      if (sql.includes('question.needs_review')) needsReview = params.needsReview;
      if (sql.includes('JSON_LENGTH(question.images)')) hasImages = sql.includes('> 0');
      if (sql.includes('question.content LIKE')) {
        keyword = String(params.keyword).replace(/%/g, '');
      }
      return this;
    },
    async getManyAndCount() {
      let rows = store.questions
        .filter((question) => !question.deleted_at)
        .map((question) => ({
          ...clone(question),
          material: question.material_id
            ? clone(
                store.materials.find(
                  (material) => material.id === question.material_id,
                ) || null,
              )
            : undefined,
        }));
      if (bankId) rows = rows.filter((question) => question.bank_id === bankId);
      if (taskId) rows = rows.filter((question) => question.parse_task_id === taskId);
      if (status) rows = rows.filter((question) => question.status === status);
      if (typeof needsReview === 'boolean') {
        rows = rows.filter((question) => question.needs_review === needsReview);
      }
      if (typeof hasImages === 'boolean') {
        rows = rows.filter((question) =>
          hasImages ? question.images.length > 0 : question.images.length === 0,
        );
      }
      if (keyword) rows = rows.filter((question) => question.content.includes(keyword as string));
      rows = sortRows(rows, { [sortBy]: sortOrder });
      return [rows.slice(offset, offset + limit), rows.length] as const;
    },
  };
}

function createRepository<T extends Record<string, any>>(
  rows: T[],
  extras: Record<string, any> = {},
) {
  return {
    create(payload: Partial<T>) {
      return payload as T;
    },
    async findOne(options: { where: Record<string, any> }) {
      const row = rows.find((item) => !item.deleted_at && matchesWhere(item, options.where));
      return row ? clone(row) : null;
    },
    async find(options: { where?: Record<string, any>; order?: Record<string, 'ASC' | 'DESC'> } = {}) {
      const filtered = rows.filter(
        (item) => !item.deleted_at && matchesWhere(item, options.where),
      );
      return clone(sortRows(filtered, options.order));
    },
    async count(options: { where?: Record<string, any> } = {}) {
      return rows.filter(
        (item) => !item.deleted_at && matchesWhere(item, options.where),
      ).length;
    },
    async update(criteria: string | Record<string, any>, patch: Partial<T>) {
      for (const row of rows) {
        const matched =
          typeof criteria === 'string'
            ? row.id === criteria
            : matchesWhere(row, criteria as Record<string, any>);
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
    createQueryBuilder() {
      throw new Error('query builder not configured');
    },
    ...extras,
  };
}

function createHarness() {
  const now = new Date('2026-04-29T10:00:00.000Z');
  const store: Store = {
    banks: [
      {
        id: 'bank-1',
        name: 'Bank One',
        subject: '行测',
        source: 'pdf',
        year: 2026,
        status: BankStatus.Draft,
        total_count: 1,
        created_at: now,
      },
    ],
    tasks: [
      {
        id: 'task-1',
        bank_id: 'bank-1',
        file_url: 'https://example.test/book.pdf',
        file_name: 'book.pdf',
        status: ParseTaskStatus.Done,
        progress: 100,
        total_count: 2,
        done_count: 2,
        attempt: 0,
        created_at: now,
      },
    ],
    materials: [
      {
        id: 'material-1',
        bank_id: 'bank-1',
        parse_task_id: 'task-1',
        content: '材料一',
        images: [{ url: 'https://example.test/material.png' }],
        page_range: [3, 3],
        created_at: now,
      },
    ],
    questions: [
      {
        id: 'question-1',
        bank_id: 'bank-1',
        material_id: 'material-1',
        parse_task_id: 'task-1',
        index_num: 2,
        type: QuestionType.Single,
        content: '第二题题干',
        option_a: 'A2',
        option_b: 'B2',
        option_c: 'C2',
        option_d: 'D2',
        answer: 'B',
        analysis: '解析二',
        images: [{ url: 'https://example.test/q2.png' }],
        status: QuestionStatus.Draft,
        needs_review: true,
        page_num: 3,
        source_page_start: 3,
        source_page_end: 3,
        created_at: now,
      },
      {
        id: 'question-2',
        bank_id: 'bank-1',
        material_id: 'material-1',
        parse_task_id: 'task-1',
        index_num: 1,
        type: QuestionType.Single,
        content: '第一题题干',
        option_a: 'A1',
        option_b: 'B1',
        option_c: 'C1',
        option_d: 'D1',
        answer: 'A',
        analysis: '解析一',
        images: [],
        status: QuestionStatus.Draft,
        needs_review: true,
        page_num: 2,
        source_page_start: 2,
        source_page_end: 2,
        created_at: now,
      },
      {
        id: 'question-3',
        bank_id: 'bank-1',
        material_id: null,
        parse_task_id: 'other-task',
        index_num: 3,
        type: QuestionType.Judge,
        content: '已发布旧题',
        option_a: '正确',
        option_b: '错误',
        answer: 'A',
        analysis: '旧解析',
        images: [],
        status: QuestionStatus.Published,
        needs_review: false,
        page_num: 1,
        source_page_start: 1,
        source_page_end: 1,
        created_at: now,
      },
      {
        id: 'question-4',
        bank_id: 'bank-1',
        material_id: null,
        parse_task_id: 'task-1',
        index_num: 99,
        type: QuestionType.Single,
        content: '其他草稿题',
        option_a: 'A',
        option_b: 'B',
        answer: 'A',
        analysis: '不应导出',
        images: [],
        status: QuestionStatus.Draft,
        needs_review: false,
        page_num: 8,
        source_page_start: 8,
        source_page_end: 8,
        deleted_at: new Date('2026-04-29T11:00:00.000Z'),
        created_at: now,
      },
    ],
  };

  const bankRepository = createRepository(store.banks, {
    createQueryBuilder: () => createBankQueryBuilder(store),
  });
  const materialRepository = createRepository(store.materials);
  const questionRepository = createRepository(store.questions, {
    createQueryBuilder: () => createQuestionQueryBuilder(store),
  });
  const taskRepository = createRepository(store.tasks);
  const systemConfigRepository = createRepository([]);

  const bankService = new BankService(
    bankRepository as any,
    questionRepository as any,
    materialRepository as any,
  );
  const questionService = new QuestionService(
    questionRepository as any,
    createRepository([]) as any,
    materialRepository as any,
    bankRepository as any,
    taskRepository as any,
    systemConfigRepository as any,
    { get: (_key: string, fallback?: string) => fallback } as any,
  );
  const pdfService = new PdfService(
    taskRepository as any,
    questionRepository as any,
    materialRepository as any,
    bankRepository as any,
    systemConfigRepository as any,
    { get: (_key: string, fallback?: string) => fallback } as any,
    {} as any,
  );

  return {
    store,
    bankService,
    questionService,
    pdfService,
    apiBankController: new ApiBankController(bankService),
    apiQuestionController: new ApiQuestionController(questionService),
  };
}

async function run() {
  await testPublishResultMakesBankVisibleToH5();
  await testExportJsonReturnsPublishedShape();
  await testPublishResultRejectsNonDoneTask();
}

async function testPublishResultMakesBankVisibleToH5() {
  const harness = createHarness();

  const result = await harness.pdfService.publishResult('task-1', {
    publish_bank: true,
  });

  assert.deepEqual(result, {
    task_id: 'task-1',
    bank_id: 'bank-1',
    published_count: 2,
    bank_status: BankStatus.Published,
    total_count: 3,
  });
  assert.equal(harness.store.banks[0].total_count, 3);
  assert.equal(harness.store.questions[0].status, QuestionStatus.Published);
  assert.equal(harness.store.questions[0].needs_review, false);

  const bankList = await harness.apiBankController.list({ page: 1, pageSize: 20 });
  assert.equal(bankList.total, 1);
  assert.equal(bankList.list[0].id, 'bank-1');

  const questionList = await harness.apiQuestionController.list({
    bankId: 'bank-1',
  } as any);
  assert.equal(questionList.total, 3);
  assert.deepEqual(
    questionList.list.map((question) => question.index_num),
    [1, 2, 3],
  );
}

async function testExportJsonReturnsPublishedShape() {
  const harness = createHarness();
  await harness.pdfService.publishResult('task-1', { publish_bank: true });

  const result = await harness.bankService.exportJson('bank-1');

  assert.equal(result.bank.id, 'bank-1');
  assert.equal(result.materials.length, 1);
  assert.deepEqual(
    result.questions.map((question: any) => question.index_num),
    [1, 2, 3],
  );
  assert.deepEqual(result.questions[0], {
    id: 'question-2',
    index_num: 1,
    type: QuestionType.Single,
    stem: '第一题题干',
    options: {
      A: 'A1',
      B: 'B1',
      C: 'C1',
      D: 'D1',
    },
    answer: 'A',
    analysis: '解析一',
    images: [],
    material_group: 'material-1',
    source_page: {
      page_num: 2,
      start: 2,
      end: 2,
    },
  });
}

async function testPublishResultRejectsNonDoneTask() {
  const harness = createHarness();
  harness.store.tasks[0].status = ParseTaskStatus.Processing;

  await assert.rejects(
    () => harness.pdfService.publishResult('task-1', {}),
    /只有已完成的解析任务才能发布结果/,
  );
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
