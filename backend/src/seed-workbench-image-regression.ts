import { NestFactory } from '@nestjs/core';
import { getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { AppModule } from './app.module';
import { BankStatus, QuestionBank } from './modules/bank/entities/question-bank.entity';
import {
  Question,
  QuestionReviewStatus,
  QuestionStatus,
  QuestionType,
} from './modules/question/entities/question.entity';

interface ImageSeed {
  url: string;
  ref: string;
  caption: string;
  role: 'question_visual' | 'option_image';
  image_role: 'question_visual' | 'option_image';
  insert_position: 'above_stem' | 'below_stem' | 'above_options' | 'below_options';
}

interface SeedQuestion {
  index_num: number;
  type: QuestionType;
  content: string;
  option_a: string;
  option_b: string;
  option_c?: string;
  option_d?: string;
  answer: string;
  analysis: string;
  images: ImageSeed[];
}

const BANK_NAME = '图片位置回归测试题库';

const questions: SeedQuestion[] = [
  {
    index_num: 1,
    type: QuestionType.Single,
    content: '图中显示的信息用于哪类题意？请选择正确判断。',
    option_a: '资料题说明题干背景',
    option_b: '问题与题干无关',
    option_c: '可忽略该图',
    option_d: '题目已损坏',
    answer: 'A',
    analysis: '该题目中的图位于题干下方，属于题干补充信息。',
    images: [
      {
        url: 'https://picsum.photos/id/1060/1200/640',
        ref: 'q1-stem-below',
        caption: '题干下方图',
        role: 'question_visual',
        image_role: 'question_visual',
        insert_position: 'below_stem',
      },
    ],
  },
  {
    index_num: 2,
    type: QuestionType.Single,
    content: '观察下图后，哪项最符合题意？',
    option_a: '该图说明题目已给条件A',
    option_b: '该图用于补充材料',
    option_c: '该图用于干扰阅读',
    option_d: '该图只作为装饰',
    answer: 'A',
    analysis: '此图应置于选项上方，属于选项区视觉材料。',
    images: [
      {
        url: 'https://picsum.photos/id/1025/1200/640',
        ref: 'q2-options-above',
        caption: '选项上方图',
        role: 'option_image',
        image_role: 'option_image',
        insert_position: 'above_options',
      },
    ],
  },
  {
    index_num: 3,
    type: QuestionType.Single,
    content: '下图在题号前应归于哪个位置？',
    option_a: '题干下方',
    option_b: '题干上方',
    option_c: '选项区',
    option_d: '解析区',
    answer: 'B',
    analysis: '题目 3 要求验证“上部”位置，使用 above_stem。',
    images: [
      {
        url: 'https://picsum.photos/id/1040/1200/640',
        ref: 'q3-stem-above',
        caption: '题干上方图',
        role: 'question_visual',
        image_role: 'question_visual',
        insert_position: 'above_stem',
      },
    ],
  },
  {
    index_num: 4,
    type: QuestionType.Single,
    content: '以下说法最接近“无图片”的定义。',
    option_a: '题干与选项都不带图像',
    option_b: '仅题干含图像',
    option_c: '仅选项含图像',
    option_d: '仅解析含图像',
    answer: 'A',
    analysis: '本题为无图片题，images 为空数组。',
    images: [],
  },
  {
    index_num: 5,
    type: QuestionType.Single,
    content: '这是多选项场景下的图片题，图片用于辅助判断下列哪一项更合理？',
    option_a: '对',
    option_b: '错',
    option_c: '无法判断',
    option_d: '与题无关',
    answer: 'A',
    analysis: '该题用于验证有图题在包含多个选项场景下的保存与回读。',
    images: [
      {
        url: 'https://picsum.photos/id/1050/1200/640',
        ref: 'q5-option-image',
        caption: '多选项图-选项区',
        role: 'option_image',
        image_role: 'option_image',
        insert_position: 'below_options',
      },
    ],
  },
];

async function bootstrap() {
  const app = await NestFactory.createApplicationContext(AppModule);
  const bankRepository = app.get<Repository<QuestionBank>>(getRepositoryToken(QuestionBank));
  const questionRepository = app.get<Repository<Question>>(
    getRepositoryToken(Question),
  );

  let bank = await bankRepository.findOne({ where: { name: BANK_NAME } });
  if (!bank) {
    bank = await bankRepository.save(
      bankRepository.create({
        name: BANK_NAME,
        subject: '行测',
        source: '人工回归',
        year: 2026,
        status: BankStatus.Published,
        total_count: 0,
      }),
    );
  } else {
    await bankRepository.update(bank.id, {
      subject: bank.subject || '行测',
      source: bank.source || '人工回归',
      year: bank.year || 2026,
      status: BankStatus.Published,
    });
  }

  for (const seed of questions) {
    const exists = await questionRepository.findOne({
      where: { bank_id: bank.id, index_num: seed.index_num },
    });

    const payload = {
      bank_id: bank.id,
      index_num: seed.index_num,
      type: seed.type,
      content: seed.content,
      option_a: seed.option_a,
      option_b: seed.option_b,
      option_c: seed.option_c || null,
      option_d: seed.option_d || null,
      answer: seed.answer,
      analysis: seed.analysis,
      images: seed.images,
      status: QuestionStatus.Published,
      needs_review: false,
      review_status: QuestionReviewStatus.Approved,
      source: '图片位置回归测试题库',
    };

    if (exists) {
      await questionRepository.update(exists.id, payload);
    } else {
      await questionRepository.save(questionRepository.create(payload));
    }
  }

  const total = await questionRepository.count({
    where: { bank_id: bank.id, status: QuestionStatus.Published },
  });
  await bankRepository.update(bank.id, { total_count: total });

  await app.close();
  console.log(`seed complete: ${BANK_NAME}`);
}

bootstrap().catch((error) => {
  console.error(error);
  process.exit(1);
});
