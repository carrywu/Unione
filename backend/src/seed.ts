import { NestFactory } from '@nestjs/core';
import { getRepositoryToken } from '@nestjs/typeorm';
import * as bcrypt from 'bcryptjs';
import { Repository } from 'typeorm';
import { AppModule } from './app.module';
import {
  BankStatus,
  QuestionBank,
} from './modules/bank/entities/question-bank.entity';
import {
  Question,
  QuestionStatus,
  QuestionType,
} from './modules/question/entities/question.entity';
import { UserRecord } from './modules/record/entities/user-record.entity';
import { User, UserRole } from './modules/user/entities/user.entity';
import {
  SystemConfig,
  SystemConfigValueType,
} from './modules/system/entities/system-config.entity';
import { ParseTask, ParseTaskStatus } from './modules/pdf/entities/parse-task.entity';

interface SeedQuestion {
  index_num: number;
  type: QuestionType;
  content: string;
  option_a?: string;
  option_b?: string;
  option_c?: string;
  option_d?: string;
  answer: string;
  analysis: string;
  status?: QuestionStatus;
  needs_review?: boolean;
}

interface SeedBank {
  name: string;
  subject: string;
  source: string;
  year: number;
  legacyNames?: string[];
  questions: SeedQuestion[];
}

const seedBanks: SeedBank[] = [
  {
    name: '2024 行测模拟题',
    subject: '行测',
    source: 'Mock',
    year: 2024,
    questions: [
      { index_num: 1, type: QuestionType.Single, content: '某单位共有 50 人，其中党员 20 人，党员占总人数的百分比是多少？', option_a: '20%', option_b: '30%', option_c: '40%', option_d: '50%', answer: 'C', analysis: '20 / 50 = 40%。' },
      { index_num: 2, type: QuestionType.Single, content: '从 1、2、3、4 中任取两个不同数字组成两位数，可以组成多少个不同的两位数？', option_a: '6', option_b: '8', option_c: '10', option_d: '12', answer: 'D', analysis: '十位有 4 种选择，个位有 3 种选择，共 4 x 3 = 12 种。' },
      { index_num: 3, type: QuestionType.Judge, content: '判断：所有偶数都能被 2 整除。', answer: '对', analysis: '偶数的定义就是能被 2 整除的整数。' },
      { index_num: 4, type: QuestionType.Single, content: '下列哪一项更符合”削足适履”的含义？', option_a: '根据实际调整方案', option_b: '机械迁就既定条件', option_c: '因地制宜解决问题', option_d: '提前准备避免风险', answer: 'B', analysis: '削足适履比喻不合理地迁就现成条件。', status: QuestionStatus.Draft, needs_review: true },
      { index_num: 5, type: QuestionType.Single, content: '某商品原价 200 元，打八折后再打九折，最终价格是多少元？', option_a: '128', option_b: '144', option_c: '160', option_d: '180', answer: 'B', analysis: '200 × 0.8 × 0.9 = 144 元。' },
      { index_num: 6, type: QuestionType.Single, content: '从甲地到乙地，客车需 3 小时，货车需 4 小时，两车同时从两地相对开出，几小时后相遇？', option_a: '12/7', option_b: '7/2', option_c: '2', option_d: '3.5', answer: 'A', analysis: '相遇时间 = 1 / (1/3 + 1/4) = 12/7 小时。' },
      { index_num: 7, type: QuestionType.Judge, content: '判断：一个数如果能被 3 和 4 整除，则一定能被 12 整除。', answer: '对', analysis: '3 和 4 互质，所以能被两者整除等价于能被 12 整除。' },
      { index_num: 8, type: QuestionType.Single, content: '某一数列前三项为 2、6、12，按此规律第 5 项是多少？', option_a: '20', option_b: '30', option_c: '36', option_d: '42', answer: 'B', analysis: '通项公式 n(n+1)，第 5 项 = 5×6 = 30。' },
      { index_num: 9, type: QuestionType.Single, content: '某班 40 人中，男生 22 人，女生 18 人。随机抽一人，抽到女生的概率是？', option_a: '11/20', option_b: '9/20', option_c: '1/2', option_d: '2/5', answer: 'B', analysis: '18/40 = 9/20。' },
      { index_num: 10, type: QuestionType.Single, content: '一项工程，甲单独做 10 天完成，乙单独做 15 天完成。两人合作需要多少天？', option_a: '5', option_b: '6', option_c: '7', option_d: '8', answer: 'B', analysis: '1 / (1/10 + 1/15) = 1 / (5/30) = 6 天。' },
    ],
  },
  {
    name: '超格夸夸刷',
    subject: '行测',
    source: '超格',
    year: 2024,
    questions: [
      { index_num: 1, type: QuestionType.Single, content: '某资料显示，2023 年 A 市 GDP 为 8400 亿元，同比增长 5%。若保持同样增速，2024 年 GDP 约为多少亿元？', option_a: '8610', option_b: '8720', option_c: '8820', option_d: '9000', answer: 'C', analysis: '8400 x 1.05 = 8820 亿元。' },
      { index_num: 2, type: QuestionType.Single, content: '甲、乙两车同时从相距 360 千米的两地相向而行，甲车每小时 80 千米，乙车每小时 70 千米，几小时后相遇？', option_a: '2', option_b: '2.4', option_c: '3', option_d: '3.6', answer: 'B', analysis: '相遇时间 = 360 / (80 + 70) = 2.4 小时。' },
      { index_num: 3, type: QuestionType.Single, content: '”因噎废食”最接近下列哪种做法？', option_a: '及时调整计划', option_b: '因小问题否定整体', option_c: '集中力量突破重点', option_d: '根据经验优化流程', answer: 'B', analysis: '因噎废食比喻因为一点问题就停止本应继续做的事。' },
      { index_num: 4, type: QuestionType.Single, content: '某工厂生产一批零件，合格率为 95%，500 个零件中约有多少个不合格？', option_a: '15', option_b: '20', option_c: '25', option_d: '30', answer: 'C', analysis: '500 × (1-0.95) = 25 个。' },
      { index_num: 5, type: QuestionType.Single, content: '一个水池，进水管 A 2 小时注满，进水管 B 3 小时注满，出水管 C 4 小时放空。三管齐开，几小时注满？', option_a: '12/7', option_b: '12/5', option_c: '12/13', option_d: '12/11', answer: 'A', analysis: '1/(1/2+1/3-1/4) = 1/(6/12+4/12-3/12) = 12/7 小时。' },
      { index_num: 6, type: QuestionType.Judge, content: '判断：百分数最大的不足 100%。', answer: '错', analysis: '增长率可以超过 100%，如增长 150%。' },
      { index_num: 7, type: QuestionType.Single, content: '某公司 2022 年销售额 600 万，2023 年 750 万，同比增长多少？', option_a: '20%', option_b: '25%', option_c: '30%', option_d: '35%', answer: 'B', analysis: '(750-600)/600 = 25%。' },
      { index_num: 8, type: QuestionType.Single, content: '把一个圆柱体削成最大圆锥体，削去部分的体积是 60 立方厘米，原来圆柱的体积是多少？', option_a: '80', option_b: '90', option_c: '100', option_d: '120', answer: 'B', analysis: '削去部分占圆柱 2/3，圆柱体积 = 60 ÷ (2/3) = 90。' },
    ],
  },
  {
    name: '超格超大杯',
    subject: '行测',
    source: '超格',
    year: 2024,
    questions: [
      { index_num: 1, type: QuestionType.Single, content: '某班男生人数比女生多 20%，男生 30 人，则女生有多少人？', option_a: '20', option_b: '24', option_c: '25', option_d: '28', answer: 'C', analysis: '女生人数 = 30 / 1.2 = 25 人。' },
      { index_num: 2, type: QuestionType.Single, content: '把 12 个相同的小球放入 3 个不同盒子，每盒至少 1 个，有多少种放法？', option_a: '45', option_b: '55', option_c: '66', option_d: '78', answer: 'B', analysis: '正整数解 x+y+z=12，方法数为 C(11,2)=55。' },
      { index_num: 3, type: QuestionType.Judge, content: '判断：三角形任意两边之和大于第三边。', answer: '对', analysis: '这是三角形成立的基本条件。' },
      { index_num: 4, type: QuestionType.Single, content: '从 0、1、2、3、4 中任取三个不同数字组成三位偶数，可以组成多少个？', option_a: '24', option_b: '30', option_c: '36', option_d: '48', answer: 'B', analysis: '个位为 0：P(4,2)=12；个位为 2 或 4 且百位不为 0：2×3×3=18。共 30 个。' },
      { index_num: 5, type: QuestionType.Single, content: '某单位 60 人参加考试，平均分 72 分。其中男生平均 68 分，女生平均 78 分。女生有多少人？', option_a: '20', option_b: '24', option_c: '30', option_d: '36', answer: 'B', analysis: '设女生 x 人，68(60-x)+78x=72×60，解得 x=24。' },
      { index_num: 6, type: QuestionType.Single, content: '甲、乙两人跑步，甲跑一圈需 3 分钟，乙需 4 分钟。两人同时同地同向出发，几分钟后甲第一次追上乙？', option_a: '8', option_b: '10', option_c: '12', option_d: '15', answer: 'C', analysis: '追及时间 = 1/(1/3-1/4) = 12 分钟。' },
      { index_num: 7, type: QuestionType.Single, content: '一个容器装满 10 升纯酒精，倒出 2 升后用水加满，再倒出 2 升再用水加满，此时酒精浓度是多少？', option_a: '60%', option_b: '64%', option_c: '72%', option_d: '80%', answer: 'B', analysis: '每次剩余 80%，两次后浓度 = 0.8² = 64%。' },
      { index_num: 8, type: QuestionType.Judge, content: '判断：平方数一定有奇数个正因数。', answer: '对', analysis: '平方数的质因数指数全为偶数，正因数个数为奇数。' },
    ],
  },
  {
    name: '花生十三资料分析600',
    subject: '行测',
    source: '花生十三',
    year: 2024,
    legacyNames: ['四海资料分析600题'],
    questions: [
      { index_num: 1, type: QuestionType.Single, content: '某地区 2022 年粮食产量为 500 万吨，2023 年为 540 万吨，则同比增长率为多少？', option_a: '6%', option_b: '7%', option_c: '8%', option_d: '9%', answer: 'C', analysis: '(540 - 500) / 500 = 8%。' },
      { index_num: 2, type: QuestionType.Single, content: '某企业一季度销售额 1200 万元，二季度比一季度增长 15%，二季度销售额是多少万元？', option_a: '1320', option_b: '1350', option_c: '1380', option_d: '1400', answer: 'C', analysis: '1200 x 1.15 = 1380 万元。' },
      { index_num: 3, type: QuestionType.Single, content: '某项指标从 80 增加到 100，增长量为多少？', option_a: '20', option_b: '25', option_c: '80', option_d: '100', answer: 'A', analysis: '增长量 = 现期量 - 基期量 = 100 - 80 = 20。' },
      { index_num: 4, type: QuestionType.Single, content: '某市 2023 年常住人口为 320 万人，比 2020 年增加 20 万人，年均增长约多少人？', option_a: '5 万', option_b: '6.67 万', option_c: '7.5 万', option_d: '10 万', answer: 'B', analysis: '20 / 3 ≈ 6.67 万人/年。' },
      { index_num: 5, type: QuestionType.Single, content: '某地 2022 年 GDP 为 2000 亿元，2023 年比 2022 年增长 8%，则增长量约为多少亿元？', option_a: '140', option_b: '150', option_c: '160', option_d: '180', answer: 'C', analysis: '2000 × 8% = 160 亿元。' },
      { index_num: 6, type: QuestionType.Single, content: '某项目原计划投资 5000 万元，实际投资 4200 万元，节约了多少？', option_a: '12%', option_b: '14%', option_c: '16%', option_d: '18%', answer: 'C', analysis: '(5000-4200)/5000 = 800/5000 = 16%。' },
      { index_num: 7, type: QuestionType.Judge, content: '判断：同比是和去年同月/同季度比的增长率。', answer: '对', analysis: '同比的定义就是与历史同期相比较。' },
      { index_num: 8, type: QuestionType.Single, content: '某公司有职员 400 人，其中女性 160 人，女性占比是多少？', option_a: '35%', option_b: '40%', option_c: '45%', option_d: '50%', answer: 'B', analysis: '160/400 = 40%。' },
    ],
  },
  {
    name: '粉笔判断推理500题',
    subject: '行测',
    source: '粉笔',
    year: 2025,
    questions: [
      {
        index_num: 1,
        type: QuestionType.Single,
        content: '甲、乙、丙三人中只有一人说真话。甲说乙说假话，乙说丙说假话，丙说甲和乙都说假话。谁说真话？',
        option_a: '甲',
        option_b: '乙',
        option_c: '丙',
        option_d: '无法确定',
        answer: 'B',
        analysis: '代入验证可知乙为真时，甲和丙均为假，满足只有一人说真话。',
      },
      {
        index_num: 2,
        type: QuestionType.Single,
        content: '电脑：程序员 与 下列哪组关系最相似？',
        option_a: '画笔：画家',
        option_b: '医院：医生',
        option_c: '课本：学生',
        option_d: '厨房：厨师',
        answer: 'A',
        analysis: '电脑是程序员常用工具，画笔是画家常用工具。',
      },
      {
        index_num: 3,
        type: QuestionType.Single,
        content: '所有 A 都是 B，部分 B 是 C。由此一定能推出的是：',
        option_a: '部分 A 是 C',
        option_b: '部分 C 是 A',
        option_c: '有些 B 是 A',
        option_d: '所有 C 都是 B',
        answer: 'C',
        analysis: '所有 A 都是 B，可推出存在 A 时有些 B 是 A；其余结论不必然。',
      },
      {
        index_num: 4,
        type: QuestionType.Single,
        content: '某公司规定：只有通过笔试才能参加面试。小王没有参加面试，可以推出：',
        option_a: '小王没有通过笔试',
        option_b: '小王通过了笔试',
        option_c: '不能确定小王是否通过笔试',
        option_d: '小王没有报名',
        answer: 'C',
        analysis: '通过笔试是参加面试的必要条件，否定后件不能否定前件。',
      },
      {
        index_num: 5,
        type: QuestionType.Judge,
        content: '判断：如果一个论证的前提真实，则结论一定真实。',
        answer: '错',
        analysis: '还需要论证形式有效，前提真实不必然保证结论真实。',
      },
    ],
  },
  {
    name: '华图言语理解精选',
    subject: '行测',
    source: '华图',
    year: 2025,
    questions: [
      {
        index_num: 1,
        type: QuestionType.Single,
        content: '填入横线处最恰当的是：数字治理不能只追求效率，还要兼顾公平，否则技术优势可能被____。',
        option_a: '消解',
        option_b: '夸大',
        option_c: '复制',
        option_d: '隐藏',
        answer: 'A',
        analysis: '语境强调优势被削弱，“消解”最合适。',
      },
      {
        index_num: 2,
        type: QuestionType.Single,
        content: '下列成语使用正确的是：',
        option_a: '他对工作不以为然，认真负责',
        option_b: '会议开得不温不火，气氛热烈',
        option_c: '这篇文章观点鲜明，鞭辟入里',
        option_d: '他们萍水相逢多年，感情深厚',
        answer: 'C',
        analysis: '“鞭辟入里”形容分析透彻，使用正确。',
      },
      {
        index_num: 3,
        type: QuestionType.Single,
        content: '主旨概括：城市更新不是简单拆旧建新，而是要在改善居住条件的同时保留历史记忆。',
        option_a: '城市更新应重视商业价值',
        option_b: '城市更新要兼顾民生改善与文化延续',
        option_c: '城市更新主要解决住房短缺',
        option_d: '历史街区不应进行改造',
        answer: 'B',
        analysis: '文段强调改善条件和保留历史记忆并重。',
      },
      {
        index_num: 4,
        type: QuestionType.Single,
        content: '填入横线处最恰当的是：面对复杂问题，治理者需要避免____，以系统思维统筹推进。',
        option_a: '见微知著',
        option_b: '头痛医头',
        option_c: '未雨绸缪',
        option_d: '因势利导',
        answer: 'B',
        analysis: '“头痛医头”指只解决表面局部问题，与系统思维相对。',
      },
    ],
  },
  {
    name: '申论小题规范表达',
    subject: '申论',
    source: '半月谈',
    year: 2025,
    questions: [
      {
        index_num: 1,
        type: QuestionType.Single,
        content: '概括题作答最应优先保证的是：',
        option_a: '文采华丽',
        option_b: '要点准确完整',
        option_c: '篇幅越长越好',
        option_d: '引用政策越多越好',
        answer: 'B',
        analysis: '概括题核心在于准确提炼材料要点。',
      },
      {
        index_num: 2,
        type: QuestionType.Single,
        content: '提出对策题中，对策应当主要来源于：',
        option_a: '个人经验',
        option_b: '网络热词',
        option_c: '材料问题和原因',
        option_d: '固定模板',
        answer: 'C',
        analysis: '对策要针对材料中的问题、原因和已有经验。',
      },
      {
        index_num: 3,
        type: QuestionType.Judge,
        content: '判断：申论答案可以完全脱离材料自由发挥。',
        answer: '错',
        analysis: '申论小题必须紧扣材料，不能脱离材料自由发挥。',
      },
    ],
  },
];

const mockUsers = [
  { phone: '13900139000', nickname: '刷题用户' },
  { phone: '13900000001', nickname: '晨读刷题王' },
  { phone: '13900000002', nickname: '资料分析练习生' },
  { phone: '13900000003', nickname: '言语小能手' },
  { phone: '13900000004', nickname: '判断推理冲刺' },
  { phone: '13900000005', nickname: '申论稳住' },
  { phone: '13900000006', nickname: '每日二十题' },
  { phone: '13900000007', nickname: '错题清零计划' },
  { phone: '13900000008', nickname: '上岸预备役' },
];

const seedConfigs: Array<Pick<SystemConfig, 'key' | 'value' | 'description' | 'value_type'>> = [
  {
    key: 'site_name',
    value: '刷题练习',
    value_type: SystemConfigValueType.String,
    description: '网站名称',
  },
  {
    key: 'allow_register',
    value: 'true',
    value_type: SystemConfigValueType.Boolean,
    description: '是否允许用户注册',
  },
  {
    key: 'quiz_time_limit',
    value: '30',
    value_type: SystemConfigValueType.Number,
    description: '单次答题时限（分钟）',
  },
  {
    key: 'max_upload_size_mb',
    value: '50',
    value_type: SystemConfigValueType.Number,
    description: 'PDF 上传大小限制（MB）',
  },
  {
    key: 'welcome_message',
    value: '欢迎使用刷题App',
    value_type: SystemConfigValueType.String,
    description: '首页欢迎语',
  },
  {
    key: 'DASHSCOPE_API_KEY',
    value: '',
    value_type: SystemConfigValueType.String,
    description: '阿里云百炼 API Key（用于通义千问 VL/文本模型）',
  },
  {
    key: 'DASHSCOPE_BASE_URL',
    value: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    value_type: SystemConfigValueType.String,
    description: '阿里云百炼 OpenAI 兼容接口地址',
  },
  {
    key: 'AI_VISUAL_MODEL',
    value: 'qwen-vl-max',
    value_type: SystemConfigValueType.String,
    description: 'PDF 图文解析视觉模型',
  },
  {
    key: 'AI_TEXT_MODEL',
    value: 'qwen-plus',
    value_type: SystemConfigValueType.String,
    description: 'PDF 纯文本结构化模型',
  },
];

async function bootstrap() {
  const app = await NestFactory.createApplicationContext(AppModule);
  const userRepository = app.get<Repository<User>>(getRepositoryToken(User));
  const bankRepository = app.get<Repository<QuestionBank>>(
    getRepositoryToken(QuestionBank),
  );
  const questionRepository = app.get<Repository<Question>>(
    getRepositoryToken(Question),
  );
  const recordRepository = app.get<Repository<UserRecord>>(
    getRepositoryToken(UserRecord),
  );
  const taskRepository = app.get<Repository<ParseTask>>(
    getRepositoryToken(ParseTask),
  );
  const configRepository = app.get<Repository<SystemConfig>>(
    getRepositoryToken(SystemConfig),
  );

  const password = await bcrypt.hash('123456', 10);

  await upsertUser(userRepository, {
    phone: '13800138000',
    password,
    nickname: '管理员',
    role: UserRole.Admin,
  });
  await upsertUser(userRepository, {
    phone: '13900139000',
    password,
    nickname: '刷题用户',
    role: UserRole.User,
  });
  for (const user of mockUsers) {
    await upsertUser(userRepository, {
      ...user,
      password,
      role: UserRole.User,
    });
  }

  for (const seedBank of seedBanks) {
    await upsertBank(bankRepository, questionRepository, seedBank);
  }
  await seedMockRecords(userRepository, questionRepository, recordRepository);
  await seedMockTasks(bankRepository, taskRepository);
  for (const config of seedConfigs) {
    await upsertConfig(configRepository, config);
  }

  await app.close();
  console.log('Seed completed.');
  console.log('Admin: 13800138000 / 123456');
  console.log('User:  13900139000 / 123456');
  console.log('Mock users: 13900000001-13900000008 / 123456');
}

async function upsertBank(
  bankRepository: Repository<QuestionBank>,
  questionRepository: Repository<Question>,
  seedBank: SeedBank,
) {
  let bank = await bankRepository.findOne({
    where: { name: seedBank.name, subject: seedBank.subject },
  });
  if (!bank && seedBank.legacyNames?.length) {
    bank = await bankRepository.findOne({
      where: seedBank.legacyNames.map((name) => ({
        name,
        subject: seedBank.subject,
      })),
    });
  }
  if (!bank) {
    bank = await bankRepository.save(
      bankRepository.create({
        name: seedBank.name,
        subject: seedBank.subject,
        source: seedBank.source,
        year: seedBank.year,
        status: BankStatus.Published,
        total_count: 0,
      }),
    );
  } else {
    await bankRepository.update(bank.id, {
      name: seedBank.name,
      source: seedBank.source,
      year: seedBank.year,
      status: BankStatus.Published,
    });
  }

  for (const seedQuestion of seedBank.questions) {
    const exists = await questionRepository.findOne({
      where: {
        bank_id: bank.id,
        index_num: seedQuestion.index_num,
      },
    });
    const data = {
      ...seedQuestion,
      bank_id: bank.id,
      images: [],
      status: seedQuestion.status || QuestionStatus.Published,
      needs_review: Boolean(seedQuestion.needs_review),
    };
    if (exists) {
      await questionRepository.update(exists.id, data);
    } else {
      await questionRepository.save(questionRepository.create(data));
    }
  }

  const total = await questionRepository.count({
    where: { bank_id: bank.id, status: QuestionStatus.Published },
  });
  await bankRepository.update(bank.id, { total_count: total });
}

async function upsertUser(
  repository: Repository<User>,
  data: Pick<User, 'phone' | 'password' | 'nickname' | 'role'>,
) {
  const exists = await repository.findOne({ where: { phone: data.phone } });
  if (exists) {
    await repository.update(exists.id, data);
    return;
  }
  await repository.save(repository.create(data));
}

async function upsertConfig(
  repository: Repository<SystemConfig>,
  data: Pick<SystemConfig, 'key' | 'value' | 'description' | 'value_type'>,
) {
  const exists = await repository.findOne({ where: { key: data.key } });
  if (exists) {
    await repository.update(exists.id, data);
    return;
  }
  await repository.save(repository.create(data));
}

async function seedMockRecords(
  userRepository: Repository<User>,
  questionRepository: Repository<Question>,
  recordRepository: Repository<UserRecord>,
) {
  const users = await userRepository.find({
    where: mockUsers.map((user) => ({ phone: user.phone })),
  });
  const questions = await questionRepository.find({
    where: { status: QuestionStatus.Published },
    order: { index_num: 'ASC' },
  });
  if (!users.length || !questions.length) return;

  for (const [userIndex, user] of users.entries()) {
    for (let dayOffset = 0; dayOffset < 21; dayOffset += 1) {
      const dailyCount = 6 + ((userIndex + dayOffset) % 5);
      for (let itemIndex = 0; itemIndex < dailyCount; itemIndex += 1) {
        const question =
          questions[(userIndex * 7 + dayOffset * 3 + itemIndex) % questions.length];
        const shouldCorrect = (userIndex + dayOffset + itemIndex) % 4 !== 0;
        const wrongAnswer = question.type === QuestionType.Judge
          ? question.answer === '对' ? '错' : '对'
          : nextOption(question.answer || 'A');
        const createdAt = new Date();
        createdAt.setDate(createdAt.getDate() - dayOffset);
        createdAt.setHours(8 + ((itemIndex + userIndex) % 12), (itemIndex * 7) % 60, 0, 0);
        const exists = await recordRepository.findOne({
          where: {
            user_id: user.id,
            question_id: question.id,
            created_at: createdAt,
          } as any,
        });
        if (exists) continue;
        await recordRepository.save(
          recordRepository.create({
            user_id: user.id,
            question_id: question.id,
            bank_id: question.bank_id,
            user_answer: shouldCorrect ? question.answer || '' : wrongAnswer,
            is_correct: shouldCorrect,
            time_spent: 25 + ((itemIndex + dayOffset) % 80),
            removed_from_wrong: shouldCorrect,
            is_mastered: !shouldCorrect && (itemIndex + userIndex) % 3 === 0,
            mastered_at:
              !shouldCorrect && (itemIndex + userIndex) % 3 === 0 ? createdAt : null,
            wrong_count: shouldCorrect ? 0 : 1 + ((itemIndex + dayOffset) % 3),
            last_wrong_at: shouldCorrect ? null : createdAt,
            created_at: createdAt,
          }),
        );
      }
    }
  }

  for (const question of questions) {
    const [answered, correct] = await Promise.all([
      recordRepository.count({ where: { question_id: question.id } }),
      recordRepository.count({
        where: { question_id: question.id, is_correct: true },
      }),
    ]);
    await questionRepository.update(question.id, {
      answer_count: answered,
      correct_rate: answered ? Number(((correct / answered) * 100).toFixed(1)) : 0,
    });
  }
}

async function seedMockTasks(
  bankRepository: Repository<QuestionBank>,
  taskRepository: Repository<ParseTask>,
) {
  const banks = await bankRepository.find({ order: { created_at: 'DESC' } });
  for (const [index, bank] of banks.slice(0, 4).entries()) {
    const fileName = `${bank.name}-mock-${index + 1}.pdf`;
    const exists = await taskRepository.findOne({
      where: { bank_id: bank.id, file_name: fileName },
    });
    const status = index === 0 ? ParseTaskStatus.Done : index === 1 ? ParseTaskStatus.Failed : ParseTaskStatus.Done;
    const data = {
      bank_id: bank.id,
      file_url: `https://mock.local/pdf/${encodeURIComponent(fileName)}`,
      file_name: fileName,
      status,
      progress: status === ParseTaskStatus.Done ? 100 : 100,
      total_count: bank.total_count,
      done_count: status === ParseTaskStatus.Done ? bank.total_count : 0,
      attempt: index === 1 ? 1 : 0,
      error: status === ParseTaskStatus.Failed ? '模拟解析失败：PDF 页码缺失' : null,
      result_summary: JSON.stringify({ mock: true, bank: bank.name }),
    };
    if (exists) {
      await taskRepository.update(exists.id, data);
    } else {
      await taskRepository.save(taskRepository.create(data));
    }
  }
}

function nextOption(answer: string) {
  const options = ['A', 'B', 'C', 'D'];
  const index = options.indexOf(answer);
  return options[(index + 1) % options.length] || 'A';
}

bootstrap().catch((error) => {
  console.error(error);
  process.exit(1);
});
