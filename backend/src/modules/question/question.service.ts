import {
  BadRequestException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { InjectRepository } from '@nestjs/typeorm';
import axios from 'axios';
import { In, Repository } from 'typeorm';
import { UserRecord } from '../record/entities/user-record.entity';
import { QuestionBank } from '../bank/entities/question-bank.entity';
import { ParseTask } from '../pdf/entities/parse-task.entity';
import { SystemConfig } from '../system/entities/system-config.entity';
import { Material } from './entities/material.entity';
import {
  Question,
  QuestionReviewStatus,
  QuestionStatus,
  QuestionType,
} from './entities/question.entity';
import { BatchDeleteQuestionDto } from './dto/batch-delete-question.dto';
import { BatchPublishDto } from './dto/batch-publish.dto';
import { CreateQuestionDto } from './dto/create-question.dto';
import {
  AddQuestionImageDto,
  AiRepairQuestionDto,
  MergeQuestionImagesDto,
  MergeQuestionDto,
  MoveQuestionImageDto,
  SplitQuestionDto,
} from './dto/question-review.dto';
import { QueryQuestionDto } from './dto/query-question.dto';
import { UpdateQuestionDto } from './dto/update-question.dto';

@Injectable()
export class QuestionService {
  constructor(
    @InjectRepository(Question)
    private readonly questionRepository: Repository<Question>,
    @InjectRepository(UserRecord)
    private readonly recordRepository: Repository<UserRecord>,
    @InjectRepository(Material)
    private readonly materialRepository: Repository<Material>,
    @InjectRepository(QuestionBank)
    private readonly bankRepository: Repository<QuestionBank>,
    @InjectRepository(ParseTask)
    private readonly taskRepository: Repository<ParseTask>,
    @InjectRepository(SystemConfig)
    private readonly systemConfigRepository: Repository<SystemConfig>,
    private readonly configService: ConfigService,
  ) {}

  async listPublished(query: QueryQuestionDto) {
    const result = await this.list(query, QuestionStatus.Published);
    result.list = result.list.map((question) => {
      const safeQuestion = { ...question };
      delete safeQuestion.answer;
      delete safeQuestion.analysis;
      delete safeQuestion.analysis_image_url;
      delete safeQuestion.answer_source_id;
      delete safeQuestion.analysis_match_confidence;
      return safeQuestion as Question;
    });
    return result;
  }

  async getAnswer(questionId: string, userId: string) {
    const question = await this.questionRepository.findOne({
      where: { id: questionId },
    });
    if (!question) {
      throw new NotFoundException('题目不存在');
    }

    const record = await this.recordRepository.findOne({
      where: { question_id: questionId, user_id: userId },
      order: { created_at: 'DESC' },
    });

    return {
      answer: question.answer,
      analysis: question.analysis,
      analysis_image_url: question.analysis_image_url,
      answer_source_id: question.answer_source_id,
      analysis_match_confidence: question.analysis_match_confidence,
      record,
    };
  }

  listAdmin(query: QueryQuestionDto) {
    return this.list(query, query.status);
  }

  async detailAdmin(id: string) {
    const question = await this.questionRepository.findOne({
      where: { id },
      relations: ['material'],
    });
    if (!question) throw new NotFoundException('题目不存在');
    const [answerCount, correctCount, task] = await Promise.all([
      this.recordRepository.count({ where: { question_id: id } }),
      this.recordRepository.count({
        where: { question_id: id, is_correct: true },
      }),
      question.parse_task_id
        ? this.taskRepository.findOne({ where: { id: question.parse_task_id } })
        : Promise.resolve(null),
    ]);
    return {
      ...this.normalizeQuestionForRead(question),
      pdf_source: task
        ? {
            task_id: task.id,
            file_url: task.file_url,
            file_name: task.file_name,
            page_num: question.page_num ?? question.page_range?.[0] ?? null,
            page_range: question.page_range || null,
            source_page_start: question.source_page_start ?? null,
            source_page_end: question.source_page_end ?? null,
            source_bbox: question.source_bbox || null,
            source_anchor_text: question.source_anchor_text || null,
            source_confidence: question.source_confidence ?? null,
          }
        : null,
      answer_count: answerCount,
      correct_rate: answerCount
        ? Number(((correctCount / answerCount) * 100).toFixed(1))
        : 0,
    };
  }

  async create(dto: CreateQuestionDto) {
    const bank = await this.bankRepository.findOne({
      where: { id: dto.bank_id },
    });
    if (!bank) throw new NotFoundException('题库不存在');

    if (dto.material_id) {
      const material = await this.materialRepository.findOne({
        where: { id: dto.material_id },
      });
      if (!material || material.bank_id !== dto.bank_id) {
        throw new BadRequestException('材料不存在或不属于该题库');
      }
    }

    if (dto.type === QuestionType.Single && (!dto.option_a || !dto.option_b)) {
      throw new BadRequestException('单选题至少需要选项 A 和 B');
    }

    const question = await this.questionRepository.save(
      this.questionRepository.create({
        ...dto,
        content: this.cleanQuestionText(dto.content),
        option_a: dto.type === QuestionType.Judge ? null : dto.option_a,
        option_b: dto.type === QuestionType.Judge ? null : dto.option_b,
        option_c: dto.type === QuestionType.Judge ? null : dto.option_c,
        option_d: dto.type === QuestionType.Judge ? null : dto.option_d,
        images: dto.images || [],
        status: dto.status || QuestionStatus.Draft,
        needs_review: false,
        review_status:
          dto.status === QuestionStatus.Published
            ? QuestionReviewStatus.Approved
            : QuestionReviewStatus.Pending,
      }),
    );
    if (question.status === QuestionStatus.Published) {
      await this.refreshBankTotal(question.bank_id);
    }
    return question;
  }

  async update(id: string, dto: UpdateQuestionDto) {
    const question = await this.questionRepository.findOne({ where: { id } });
    if (!question) {
      throw new NotFoundException('题目不存在');
    }
    const previousBankId = question.bank_id;
    const previousStatus = question.status;
    Object.assign(question, {
      ...dto,
      content:
        dto.content === undefined
          ? question.content
          : this.cleanQuestionText(dto.content),
    });
    if (dto.images !== undefined) {
      question.images = this.withImageOrder(this.normalizeImageArray(dto.images));
    }
    if (dto.status === QuestionStatus.Published) {
      question.needs_review = false;
      question.review_status = QuestionReviewStatus.Approved;
    } else if (dto.needs_review === true) {
      question.review_status = QuestionReviewStatus.NeedsReview;
    } else if (dto.needs_review === false && !dto.review_status) {
      question.review_status = QuestionReviewStatus.Pending;
    }
    const saved = await this.questionRepository.save(question);
    if (
      previousBankId !== saved.bank_id ||
      previousStatus !== saved.status ||
      dto.status
    ) {
      await Promise.all(
        [...new Set([previousBankId, saved.bank_id])].map((bankId) =>
          this.refreshBankTotal(bankId),
        ),
      );
    }
    return saved;
  }

  async reviewReadability(id: string) {
    const question = await this.questionRepository.findOne({
      where: { id },
      relations: ['material'],
    });
    if (!question) {
      throw new NotFoundException('题目不存在');
    }

    const review = await this.requestReadabilityReview(question);
    const previousWarnings = Array.isArray(question.parse_warnings)
      ? question.parse_warnings
      : [];
    const reviewWarning = 'ai_readability_needs_review';
    const nextWarnings = review.needs_review
      ? [...new Set([...previousWarnings, reviewWarning])]
      : previousWarnings;

    if (review.needs_review && !question.needs_review) {
      await this.questionRepository.update(question.id, {
        needs_review: true,
        parse_warnings: nextWarnings,
      });
    } else if (review.needs_review && nextWarnings.length !== previousWarnings.length) {
      await this.questionRepository.update(question.id, {
        parse_warnings: nextWarnings,
      });
    }

    return {
      ...review,
      marked_needs_review: Boolean(review.needs_review),
      question_id: question.id,
    };
  }

  async remove(id: string) {
    const question = await this.questionRepository.findOne({ where: { id } });
    if (!question) {
      throw new NotFoundException('题目不存在');
    }
    await this.questionRepository.softRemove(question);
    await this.refreshBankTotal(question.bank_id);
    return true;
  }

  async addQuestionImage(id: string, dto: AddQuestionImageDto) {
    const question = await this.loadQuestion(id);
    if (!dto.url && !dto.base64) {
      throw new BadRequestException('图片 url 或 base64 至少提供一个');
    }
    const images = this.normalizeImageArray(question.images);
    const image = this.normalizeQuestionImage({
      ...dto,
      role: dto.image_role || (dto as any).role || 'question_visual',
      image_role: dto.image_role || (dto as any).image_role || 'question_visual',
      insert_position: dto.insert_position || (dto as any).insert_position || 'below_stem',
    });
    images.push(image);
    question.images = this.withImageOrder(images);
    question.needs_review = true;
    question.review_status = QuestionReviewStatus.NeedsReview;
    return this.questionRepository.save(question);
  }

  async reorderQuestionImages(id: string, imageUrls: string[]) {
    const question = await this.loadQuestion(id);
    const images = this.normalizeImageArray(question.images);
    const order = new Map(imageUrls.map((url, index) => [url, index]));
    const reordered = [...images].sort((left, right) => {
      const leftOrder = order.has(this.imageKey(left))
        ? order.get(this.imageKey(left))!
        : Number.MAX_SAFE_INTEGER;
      const rightOrder = order.has(this.imageKey(right))
        ? order.get(this.imageKey(right))!
        : Number.MAX_SAFE_INTEGER;
      if (leftOrder === rightOrder) {
        return Number(left.image_order || 0) - Number(right.image_order || 0);
      }
      return leftOrder - rightOrder;
    });
    question.images = this.withImageOrder(reordered);
    question.needs_review = true;
    question.review_status = QuestionReviewStatus.NeedsReview;
    return this.questionRepository.save(question);
  }

  async deleteQuestionImage(id: string, imageKey: string) {
    const question = await this.loadQuestion(id);
    const images = this.normalizeImageArray(question.images);
    const decodedKey = this.safeDecodeComponent(imageKey);
    const imageIndex = images.findIndex(
      (image, index) =>
        this.imageKey(image) === decodedKey ||
        String(image.ref || '') === decodedKey ||
        String(index) === decodedKey,
    );
    if (imageIndex < 0) {
      throw new NotFoundException('题目图片不存在');
    }
    images.splice(imageIndex, 1);
    question.images = this.withImageOrder(images);
    question.needs_review = true;
    question.review_status = QuestionReviewStatus.NeedsReview;
    return this.questionRepository.save(question);
  }

  async mergeQuestionImages(id: string, dto: MergeQuestionImagesDto) {
    const question = await this.loadQuestion(id);
    const images = this.normalizeImageArray(question.images);
    const firstIndex = images.findIndex(
      (image) => this.imageKey(image) === dto.image_url,
    );
    if (firstIndex < 0) {
      throw new NotFoundException('题目图片不存在');
    }
    const secondIndex = dto.next_image_url
      ? images.findIndex((image) => this.imageKey(image) === dto.next_image_url)
      : firstIndex + 1;
    if (secondIndex < 0 || secondIndex >= images.length || secondIndex === firstIndex) {
      throw new BadRequestException('缺少可合并的相邻图片');
    }
    if (Math.abs(secondIndex - firstIndex) !== 1) {
      throw new BadRequestException('只能合并相邻图片');
    }
    const groupId =
      dto.same_visual_group_id ||
      images[firstIndex].same_visual_group_id ||
      images[secondIndex].same_visual_group_id ||
      `manual-visual-group-${Date.now()}`;
    images[firstIndex].same_visual_group_id = groupId;
    images[secondIndex].same_visual_group_id = groupId;
    question.images = this.withImageOrder(images);
    question.needs_review = true;
    question.review_status = QuestionReviewStatus.NeedsReview;
    return this.questionRepository.save(question);
  }

  async moveQuestionImage(id: string, dto: MoveQuestionImageDto) {
    const question = await this.loadQuestion(id);
    const images = this.normalizeImageArray(question.images);
    const imageIndex = images.findIndex(
      (image) => this.imageKey(image) === dto.image_url,
    );
    if (imageIndex < 0) {
      throw new NotFoundException('题目图片不存在');
    }
    const target = dto.target_question_id
      ? await this.loadQuestion(dto.target_question_id)
      : await this.findAdjacentQuestion(question, dto.direction || 'next');
    if (target.bank_id !== question.bank_id) {
      throw new BadRequestException('目标题目不属于同一题库');
    }
    const [moved] = images.splice(imageIndex, 1);
    const targetImages = this.normalizeImageArray(target.images);
    targetImages.push({
      ...moved,
      moved_from_question_id: question.id,
    });
    question.images = this.withImageOrder(images);
    question.needs_review = true;
    question.review_status = QuestionReviewStatus.NeedsReview;
    target.images = this.withImageOrder(targetImages);
    target.needs_review = true;
    target.review_status = QuestionReviewStatus.NeedsReview;
    await this.questionRepository.save(question);
    return this.questionRepository.save(target);
  }

  async repairQuestionWithAi(id: string, dto: AiRepairQuestionDto = {}) {
    const question = await this.questionRepository.findOne({
      where: { id },
      relations: ['material'],
    });
    if (!question) throw new NotFoundException('题目不存在');

    const pdfServiceUrl = this.configService.get<string>(
      'PDF_SERVICE_URL',
      'http://localhost:8001',
    );
    const response = await axios.post(
      `${pdfServiceUrl}/repair-question`,
      {
        question: this.buildReadabilityPayload(question),
        source: this.questionSourcePayload(question),
        neighbors: dto.include_neighbors === false
          ? null
          : await this.questionNeighborSummaries(question),
        warnings: dto.warnings || question.parse_warnings || [],
        ai_config: await this.getAiConfig(),
      },
      { timeout: 2 * 60 * 1000 },
    );
    return this.normalizeRepairProposal(response.data, question);
  }

  async splitQuestion(id: string, dto: SplitQuestionDto) {
    const question = await this.loadQuestion(id);
    const marker = String(dto.split_text || '').trim();
    if (!marker || !question.content.includes(marker)) {
      throw new BadRequestException('缺少有效拆分文本');
    }
    const [before, ...afterParts] = question.content.split(marker);
    const after = [marker, ...afterParts].join('').trim();
    if (!before.trim() || !after) {
      throw new BadRequestException('拆分后题干不能为空');
    }
    const bankQuestions = await this.sortedBankQuestions(question.bank_id);
    for (const item of bankQuestions.filter((item) => item.index_num > question.index_num)) {
      item.index_num += 1;
      await this.questionRepository.save(item);
    }
    question.content = before.trim();
    question.needs_review = true;
    question.review_status = QuestionReviewStatus.NeedsReview;
    await this.questionRepository.save(question);

    const nextPayload = (dto.next_question || {}) as Partial<Question>;
    return this.questionRepository.save(
      this.questionRepository.create({
        ...question,
        ...nextPayload,
        id: undefined,
        content: String(nextPayload.content || after).trim(),
        index_num: question.index_num + 1,
        images: nextPayload.images || [],
        status: QuestionStatus.Draft,
        needs_review: true,
        review_status: QuestionReviewStatus.NeedsReview,
      } as any),
    );
  }

  async mergeQuestion(id: string, dto: MergeQuestionDto) {
    const question = await this.loadQuestion(id);
    const target =
      dto.direction === 'previous'
        ? await this.findAdjacentQuestion(question, 'previous')
        : await this.findAdjacentQuestion(question, 'next');
    target.content = this.cleanQuestionText(
      [target.content, question.content].filter(Boolean).join('\n\n'),
    );
    target.images = this.withImageOrder([
      ...this.normalizeImageArray(target.images),
      ...this.normalizeImageArray(question.images),
    ]);
    target.needs_review = true;
    target.review_status = QuestionReviewStatus.NeedsReview;
    await this.questionRepository.save(target);
    await this.questionRepository.softRemove(question);
    return target;
  }

  async batchPublish(dto: BatchPublishDto) {
    const questions = await this.questionRepository.find({
      where: { id: In(dto.ids) },
      withDeleted: false,
    });
    await this.questionRepository.update(
      { id: In(dto.ids) },
      {
        status: QuestionStatus.Published,
        needs_review: false,
        review_status: QuestionReviewStatus.Approved,
      },
    );
    await Promise.all(
      [...new Set(questions.map((question) => question.bank_id))].map(
        (bankId) => this.refreshBankTotal(bankId),
      ),
    );
    return { count: dto.ids.length };
  }

  async batchDelete(dto: BatchDeleteQuestionDto) {
    const questions = await this.questionRepository.find({
      where: { id: In(dto.ids) },
      withDeleted: false,
    });
    const ids = questions.map((question) => question.id);
    if (ids.length) {
      await this.questionRepository.softDelete({ id: In(ids) });
      await Promise.all(
        [...new Set(questions.map((question) => question.bank_id))].map(
          (bankId) => this.refreshBankTotal(bankId),
        ),
      );
    }
    return {
      deleted_count: ids.length,
      skipped_count: dto.ids.length - ids.length,
    };
  }

  async getReviewStats(bankId: string) {
    const [total, published, needs_review, draft] = await Promise.all([
      this.questionRepository.count({ where: { bank_id: bankId } }),
      this.questionRepository.count({
        where: { bank_id: bankId, status: QuestionStatus.Published },
      }),
      this.questionRepository.count({
        where: { bank_id: bankId, needs_review: true },
      }),
      this.questionRepository.count({
        where: { bank_id: bankId, status: QuestionStatus.Draft },
      }),
    ]);

    return { total, published, needs_review, draft };
  }

  private async requestReadabilityReview(question: Question) {
    const pdfServiceUrl = this.configService.get<string>(
      'PDF_SERVICE_URL',
      'http://localhost:8001',
    );
    try {
      const response = await axios.post(
        `${pdfServiceUrl}/review-question-readability`,
        {
          question: this.buildReadabilityPayload(question),
          source: this.questionSourcePayload(question),
          ai_config: await this.getAiConfig(),
        },
        { timeout: 120000 },
      );
      return this.normalizeReadabilityReview(response.data);
    } catch (error) {
      return {
        ...this.heuristicReadabilityReview(question),
        source: 'backend_heuristic_pdf_service_failed',
        warnings: [this.resolveExternalError(error)],
      };
    }
  }

  private buildReadabilityPayload(question: Question) {
    return {
      id: question.id,
      index_num: question.index_num,
      type: question.type,
      content: question.content,
      options: {
        A: question.option_a || '',
        B: question.option_b || '',
        C: question.option_c || '',
        D: question.option_d || '',
      },
      answer: question.answer || '',
      analysis: question.analysis || '',
      material: question.material?.content || '',
      images: question.images || [],
      image_refs: question.image_refs || [],
      visual_refs: question.visual_refs || [],
      parse_warnings: question.parse_warnings || [],
    };
  }

  private questionSourcePayload(question: Question) {
    return {
      parse_task_id: question.parse_task_id || null,
      page_num: question.page_num || null,
      page_range: question.page_range || null,
      source_page_start: question.source_page_start || null,
      source_page_end: question.source_page_end || null,
      source_bbox: question.source_bbox || null,
      source_anchor_text: question.source_anchor_text || null,
    };
  }

  private normalizeReadabilityReview(value: any) {
    const focusAreas = Array.isArray(value?.focus_areas)
      ? value.focus_areas.map(String)
      : [];
    return {
      readable: Boolean(value?.readable) && !value?.needs_review,
      needs_review: Boolean(value?.needs_review),
      score: Number.isFinite(Number(value?.score)) ? Number(value.score) : 0,
      reasons: Array.isArray(value?.reasons) ? value.reasons.map(String) : [],
      prompts: Array.isArray(value?.prompts) ? value.prompts.map(String) : [],
      focus_areas: focusAreas,
      source: value?.source ? String(value.source) : 'unknown',
      warnings: Array.isArray(value?.warnings) ? value.warnings.map(String) : [],
    };
  }

  private heuristicReadabilityReview(question: Question) {
    const reasons: string[] = [];
    const prompts: string[] = [];
    const focusAreas: string[] = [];
    if (!question.content?.trim() || question.content.trim().length < 12) {
      reasons.push('题干过短或缺失');
      prompts.push('重新框选题干区域');
      focusAreas.push('stem');
    }
    if (question.type !== QuestionType.Judge) {
      const missing = [
        ['A', question.option_a],
        ['B', question.option_b],
        ['C', question.option_c],
        ['D', question.option_d],
      ]
        .filter(([, text]) => !String(text || '').trim())
        .map(([key]) => key);
      if (missing.length) {
        reasons.push(`选项缺失：${missing.join(',')}`);
        prompts.push('重新框选选项区域');
        focusAreas.push('options');
      }
    }
    if (question.parse_warnings?.length) {
      reasons.push('存在解析警告');
      prompts.push('根据解析警告复查题干、选项和图片');
      focusAreas.push('warnings');
    }
    const needsReview = reasons.length > 0;
    return {
      readable: !needsReview,
      needs_review: needsReview,
      score: needsReview ? 0.55 : 0.88,
      reasons,
      prompts,
      focus_areas: [...new Set(focusAreas)],
      source: 'backend_heuristic',
      warnings: [],
    };
  }

  private async getAiConfig() {
    const configs = await this.systemConfigRepository.find({
      where: [
        { key: 'DASHSCOPE_API_KEY' },
        { key: 'DASHSCOPE_BASE_URL' },
        { key: 'AI_VISUAL_MODEL' },
        { key: 'AI_TEXT_API_KEY' },
        { key: 'AI_TEXT_BASE_URL' },
        { key: 'AI_TEXT_MODEL' },
        { key: 'DEEPSEEK_API_KEY' },
        { key: 'DEEPSEEK_BASE_URL' },
        { key: 'DEEPSEEK_MODEL' },
        { key: 'PDF_HEADER_FOOTER_BLACKLIST' },
      ],
    });
    const values = new Map(configs.map((config) => [config.key, config.value]));
    const read = (key: string, fallback?: string) =>
      values.get(key) || this.configService.get<string>(key) || fallback || '';
    return Object.fromEntries(
      Object.entries({
        dashscope_api_key: read('DASHSCOPE_API_KEY'),
        dashscope_base_url: read(
          'DASHSCOPE_BASE_URL',
          'https://dashscope.aliyuncs.com/compatible-mode/v1',
        ),
        visual_model: read('AI_VISUAL_MODEL', 'qwen-vl-max'),
        text_api_key:
          read('AI_TEXT_API_KEY') ||
          read('DEEPSEEK_API_KEY') ||
          read('DASHSCOPE_API_KEY'),
        text_base_url:
          read('AI_TEXT_BASE_URL') ||
          read('DEEPSEEK_BASE_URL') ||
          read(
            'DASHSCOPE_BASE_URL',
            'https://dashscope.aliyuncs.com/compatible-mode/v1',
          ),
        text_model:
          read('AI_TEXT_MODEL') || read('DEEPSEEK_MODEL') || 'qwen-plus',
        deepseek_api_key: read('DEEPSEEK_API_KEY'),
        deepseek_base_url: read('DEEPSEEK_BASE_URL'),
        deepseek_model: read('DEEPSEEK_MODEL'),
        header_footer_blacklist: read('PDF_HEADER_FOOTER_BLACKLIST'),
      }).filter(([, value]) => Boolean(value)),
    );
  }

  private async loadQuestion(id: string) {
    const question = await this.questionRepository.findOne({ where: { id } });
    if (!question) throw new NotFoundException('题目不存在');
    return question;
  }

  private normalizeImageArray(value: unknown): Array<Record<string, any>> {
    if (!Array.isArray(value)) return [];
    return value
      .map((image): Record<string, any> =>
        typeof image === 'string'
          ? { url: image }
          : { ...(image as Record<string, any>) },
      )
      .filter((image) => image.url || image.base64);
  }

  private normalizeQuestionImage(image: Record<string, any>) {
    return {
      ...image,
      image_role: image.image_role || image.role || 'unknown',
      role: image.role || image.image_role || 'unknown',
      insert_position: image.insert_position || 'below_stem',
    };
  }

  private withImageOrder(images: Array<Record<string, any>>) {
    return images.map((image, index) => ({
      ...this.normalizeQuestionImage(image),
      image_order: index + 1,
    }));
  }

  private imageKey(image: Record<string, any>) {
    return String(image.url || image.ref || image.base64 || '');
  }

  private async sortedBankQuestions(bankId: string) {
    const questions = await this.questionRepository.find({
      where: { bank_id: bankId },
      order: { index_num: 'ASC' },
    });
    return questions.sort((left, right) => left.index_num - right.index_num);
  }

  private async findAdjacentQuestion(
    question: Question,
    direction: 'previous' | 'next',
  ) {
    const questions = await this.sortedBankQuestions(question.bank_id);
    const index = questions.findIndex((item) => item.id === question.id);
    const target = questions[direction === 'previous' ? index - 1 : index + 1];
    if (!target) {
      throw new NotFoundException(
        direction === 'previous' ? '上一题不存在' : '下一题不存在',
      );
    }
    return target;
  }

  private async questionNeighborSummaries(question: Question) {
    const questions = await this.sortedBankQuestions(question.bank_id);
    const index = questions.findIndex((item) => item.id === question.id);
    const summarize = (item?: Question) =>
      item
        ? {
            id: item.id,
            index_num: item.index_num,
            content: item.content,
            page_num: item.page_num || null,
          }
        : null;
    return {
      previous: summarize(questions[index - 1]),
      next: summarize(questions[index + 1]),
    };
  }

  private normalizeRepairProposal(value: any, question: Question) {
    const options = value?.options && typeof value.options === 'object'
      ? Object.fromEntries(
          ['A', 'B', 'C', 'D'].map((key) => [
            key,
            String(value.options[key] || value.options[key.toLowerCase()] || ''),
          ]),
        )
      : { A: '', B: '', C: '', D: '' };
    const warnings = Array.isArray(value?.warnings)
      ? value.warnings.map(String)
      : [];
    const content = this.cleanQuestionText(value?.content || question.content);
    if (this.hasHeaderFooterNoise(content)) {
      warnings.push('header_footer_blacklist_hit');
    }
    if (Object.values(options).some((option) => !String(option).trim())) {
      warnings.push('options_missing');
    }
    const confidence = Number(value?.confidence);
    return {
      content,
      options,
      visual_refs: Array.isArray(value?.visual_refs) ? value.visual_refs : [],
      material_text: String(value?.material_text || ''),
      remove_texts: Array.isArray(value?.remove_texts)
        ? value.remove_texts.map(String)
        : [],
      warnings: [...new Set(warnings)],
      confidence: Number.isFinite(confidence) ? confidence : 0,
      persisted: false,
    };
  }

  private hasHeaderFooterNoise(content: string) {
    return /资料分析题库|夸夸刷|第[一二三四五六七八九十百千万\d]+章/.test(content);
  }

  private safeDecodeComponent(value: string) {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  }

  private resolveExternalError(error: unknown) {
    if (axios.isAxiosError(error)) {
      const response = error.response?.data;
      return typeof response === 'string'
        ? response
        : response
          ? JSON.stringify(response)
          : error.message;
    }
    return error instanceof Error ? error.message : 'AI 预审失败';
  }

  private async list(query: QueryQuestionDto, status?: QuestionStatus) {
    const page = query.page || 1;
    const pageSize = query.pageSize || 20;
    const sortBy = query.sort_by || 'index_num';
    const sortOrder = query.sort_order || 'ASC';
    const qb = this.questionRepository
      .createQueryBuilder('question')
      .leftJoinAndMapOne(
        'question.material',
        Material,
        'material',
        'material.id = question.material_id',
      )
      .skip((page - 1) * pageSize)
      .take(pageSize);

    qb.orderBy(`question.${sortBy}`, sortOrder);

    if (query.bankId) {
      qb.andWhere('question.bank_id = :bankId', { bankId: query.bankId });
    }
    if (query.taskId) {
      qb.andWhere('question.parse_task_id = :taskId', { taskId: query.taskId });
    }
    if (status) {
      qb.andWhere('question.status = :status', { status });
    }
    if (typeof query.needsReview === 'boolean') {
      qb.andWhere('question.needs_review = :needsReview', {
        needsReview: query.needsReview,
      });
    }
    if (typeof query.has_images === 'boolean') {
      qb.andWhere(
        query.has_images
          ? 'COALESCE(JSON_LENGTH(question.images), 0) > 0'
          : 'COALESCE(JSON_LENGTH(question.images), 0) = 0',
      );
    }
    if (query.keyword) {
      qb.andWhere('question.content LIKE :keyword', {
        keyword: `%${query.keyword}%`,
      });
    }

    const [list, total] = await qb.getManyAndCount();
    return {
      list: list.map((question) => this.normalizeQuestionForRead(question)),
      total,
      page,
      pageSize,
    };
  }

  private async refreshBankTotal(bankId: string) {
    const total = await this.questionRepository.count({
      where: { bank_id: bankId, status: QuestionStatus.Published },
    });
    await this.bankRepository.update(bankId, { total_count: total });
  }

  private cleanQuestionText(value: unknown) {
    return String(value || '')
      .split(/\r?\n/)
      .filter((line) => !['【', '】', '【】'].includes(line.trim()))
      .join('\n')
      .trim()
      .replace(/^[\s\r\n]*[【】]+[\s\r\n]*/g, '')
      .replace(/[\s\r\n]*[【】]+[\s\r\n]*$/g, '')
      .trim();
  }

  private normalizeQuestionForRead<T extends Question>(question: T): T {
    question.content = this.cleanQuestionText(question.content);
    if (question.material) {
      question.material.content = this.cleanQuestionText(
        question.material.content,
      );
    }
    return question;
  }
}
