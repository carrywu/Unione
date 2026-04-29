import {
  BadRequestException,
  Injectable,
  Logger,
  NotFoundException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { InjectRepository } from '@nestjs/typeorm';
import axios from 'axios';
import { EventEmitter } from 'events';
import { Not, Repository } from 'typeorm';
import { QuestionBank } from '../bank/entities/question-bank.entity';
import {
  AnswerBookMode,
  ParseTask,
  ParseTaskStatus,
  ParseTaskType,
} from '../pdf/entities/parse-task.entity';
import { Question } from '../question/entities/question.entity';
import { SystemConfig } from '../system/entities/system-config.entity';
import { UploadService } from '../upload/upload.service';
import { BindAnswerSourceDto } from './dto/bind-answer-source.dto';
import { CreateAnswerBookDto } from './dto/create-answer-book.dto';
import { QueryAnswerSourceDto } from './dto/query-answer-source.dto';
import {
  AnswerSource,
  AnswerSourceParseMode,
  AnswerSourceStatus,
} from './entities/answer-source.entity';

@Injectable()
export class AnswerBookService {
  private readonly logger = new Logger(AnswerBookService.name);
  private readonly emitter = new EventEmitter();

  constructor(
    @InjectRepository(ParseTask)
    private readonly taskRepository: Repository<ParseTask>,
    @InjectRepository(AnswerSource)
    private readonly answerSourceRepository: Repository<AnswerSource>,
    @InjectRepository(Question)
    private readonly questionRepository: Repository<Question>,
    @InjectRepository(QuestionBank)
    private readonly bankRepository: Repository<QuestionBank>,
    @InjectRepository(SystemConfig)
    private readonly systemConfigRepository: Repository<SystemConfig>,
    private readonly configService: ConfigService,
    private readonly uploadService: UploadService,
  ) {
    this.emitter.on('parse-answer-book', (taskId: string) => {
      void this.processAnswerBookTask(taskId);
    });
  }

  async create(bankId: string, dto: CreateAnswerBookDto) {
    const bank = await this.bankRepository.findOne({ where: { id: bankId } });
    if (!bank) throw new NotFoundException('题库不存在');

    const task = await this.taskRepository.save(
      this.taskRepository.create({
        bank_id: bankId,
        file_url: dto.file_url,
        file_name: dto.file_name || this.resolveFileName(dto.file_url),
        task_type: ParseTaskType.AnswerBook,
        answer_book_mode: dto.mode || AnswerBookMode.Auto,
        status: ParseTaskStatus.Pending,
        progress: 0,
      }),
    );
    setImmediate(() => this.emitter.emit('parse-answer-book', task.id));
    return { task_id: task.id };
  }

  async matchTask(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    const sources = await this.answerSourceRepository.find({
      where: { parse_task_id: taskId },
      order: { question_index: 'ASC', source_page_num: 'ASC' },
    });
    const result = await this.matchSources(task.bank_id, sources);
    await this.updateTaskMatchSummary(task, result);
    return result;
  }

  listSources(query: QueryAnswerSourceDto) {
    return this.answerSourceRepository.find({
      where: {
        ...(query.bank_id ? { bank_id: query.bank_id } : {}),
        ...(query.parse_task_id ? { parse_task_id: query.parse_task_id } : {}),
        ...(query.status
          ? { status: query.status as AnswerSourceStatus }
          : { status: Not(AnswerSourceStatus.Ignored) }),
      },
      relations: ['matched_question'],
      order: { source_page_num: 'ASC', question_index: 'ASC', created_at: 'ASC' },
    });
  }

  async bind(sourceId: string, dto: BindAnswerSourceDto) {
    const source = await this.answerSourceRepository.findOne({
      where: { id: sourceId },
    });
    if (!source) throw new NotFoundException('答案源不存在');

    const question = await this.questionRepository.findOne({
      where: { id: dto.question_id },
    });
    if (!question || question.bank_id !== source.bank_id) {
      throw new BadRequestException('题目不存在或不属于该题库');
    }

    await this.applySourceToQuestion(source, question, 100);
    await this.answerSourceRepository.update(source.id, {
      status: AnswerSourceStatus.Matched,
      matched_question_id: question.id,
      match_score: 100,
    });
    return { status: AnswerSourceStatus.Matched, question_id: question.id };
  }

  async unbind(sourceId: string) {
    const source = await this.answerSourceRepository.findOne({
      where: { id: sourceId },
    });
    if (!source) throw new NotFoundException('答案源不存在');

    if (source.matched_question_id) {
      const question = await this.questionRepository.findOne({
        where: { id: source.matched_question_id },
      });
      if (question?.answer_source_id === source.id) {
        await this.questionRepository.update(question.id, {
          answer_source_id: null,
          analysis_match_confidence: null,
          ...(question.analysis_image_url === source.analysis_image_url
            ? { analysis_image_url: null }
            : {}),
          ...(question.answer === source.answer ? { answer: null } : {}),
          ...(question.analysis === source.analysis_text ? { analysis: null } : {}),
        });
      }
    }

    await this.answerSourceRepository.update(source.id, {
      status: AnswerSourceStatus.Unmatched,
      matched_question_id: null,
      match_score: null,
    });
    return { status: AnswerSourceStatus.Unmatched };
  }

  private async processAnswerBookTask(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) return;

    try {
      await this.taskRepository.update(task.id, {
        status: ParseTaskStatus.Processing,
        progress: 10,
      });
      await this.answerSourceRepository.delete({ parse_task_id: task.id });

      const pdfServiceUrl = this.configService.get<string>(
        'PDF_SERVICE_URL',
        'http://localhost:8001',
      );
      await axios.get(`${pdfServiceUrl}/health`, { timeout: 3000 });
      const response = await axios.post(
        `${pdfServiceUrl}/parse-answer-book-by-url`,
        {
          url: task.file_url,
          mode: task.answer_book_mode || AnswerBookMode.Auto,
          ai_config: await this.getAiConfig(),
        },
        { timeout: 30 * 60 * 1000 },
      );

      const rawCandidates = Array.isArray(response.data?.candidates)
        ? response.data.candidates
        : [];
      const saveResult = await this.saveSources(task, rawCandidates);
      await this.taskRepository.update(task.id, {
        progress: 70,
        total_count: saveResult.sources.length,
        done_count: saveResult.sources.length,
      });

      const matchResult = await this.matchSources(task.bank_id, saveResult.sources);
      await this.updateTaskMatchSummary(task, {
        ...matchResult,
        ignored: matchResult.ignored + saveResult.ignored,
        parsed_total: rawCandidates.length,
        mode: response.data?.mode || task.answer_book_mode,
        stats: response.data?.stats || {},
      });
      this.logger.log(
        `Done answer book task id=${task.id} sources=${saveResult.sources.length} ignored=${saveResult.ignored} matched=${matchResult.matched}`,
      );
    } catch (error) {
      const message = this.resolveErrorMessage(error);
      this.logger.error(
        `Failed answer book task id=${task.id} message=${message}`,
        error instanceof Error ? error.stack : undefined,
      );
      await this.taskRepository.update(task.id, {
        status: ParseTaskStatus.Failed,
        progress: 100,
        error: message,
      });
    }
  }

  private async saveSources(task: ParseTask, candidates: Array<Record<string, any>>) {
    const sources: AnswerSource[] = [];
    const questionIndexes = await this.getQuestionIndexSet(task.bank_id);
    let ignored = 0;
    for (const candidate of candidates) {
      if (this.isSequentialFallbackCandidate(candidate) && !questionIndexes.has(this.toNumber(candidate.question_index, 0))) {
        ignored += 1;
        continue;
      }
      const imageUrl = await this.resolveAnalysisImageUrl(task.id, candidate);
      const source = await this.answerSourceRepository.save(
        this.answerSourceRepository.create({
          bank_id: task.bank_id,
          parse_task_id: task.id,
          source_pdf_url: task.file_url,
          source_page_num: this.toNumber(candidate.source_page_num, 0),
          source_page_range: this.toNumberArray(candidate.source_page_range),
          source_bbox: this.toNumberArray(candidate.source_bbox),
          section_key: candidate.section_key || null,
          question_index: this.toNumber(candidate.question_index, 0),
          question_anchor: candidate.question_anchor || null,
          answer: candidate.answer || null,
          analysis_text: candidate.analysis_text || null,
          analysis_image_url: imageUrl,
          image_width: this.toOptionalNumber(candidate.image_width),
          image_height: this.toOptionalNumber(candidate.image_height),
          raw_text: candidate.raw_text || null,
          confidence: this.toNumber(candidate.confidence, 0),
          parse_mode:
            candidate.parse_mode === AnswerSourceParseMode.Image
              ? AnswerSourceParseMode.Image
              : AnswerSourceParseMode.Text,
          status: AnswerSourceStatus.Unmatched,
        }),
      );
      sources.push(source);
    }
    return { sources, ignored };
  }

  private async getQuestionIndexSet(bankId: string) {
    const rows = await this.questionRepository.find({
      where: { bank_id: bankId },
      select: { index_num: true },
    });
    return new Set(rows.map((question) => question.index_num));
  }

  private async resolveAnalysisImageUrl(
    taskId: string,
    candidate: Record<string, any>,
  ) {
    if (candidate.analysis_image_url) return String(candidate.analysis_image_url);
    if (!candidate.analysis_image_base64) return null;

    const upload = await this.uploadService.uploadBuffer(
      Buffer.from(String(candidate.analysis_image_base64), 'base64'),
      {
        filename: `answer-${candidate.question_index || 'block'}.png`,
        mimetype: 'image/png',
        prefix: `answer-books/${taskId}`,
      },
    );
    return upload.url;
  }

  private async matchSources(bankId: string, sources: AnswerSource[]) {
    await this.clearQuestionBindingsForSources(sources);

    const questions = await this.questionRepository.find({
      where: { bank_id: bankId },
      order: { index_num: 'ASC', created_at: 'ASC' },
    });
    const byIndex = new Map<number, Question[]>();
    for (const question of questions) {
      const list = byIndex.get(question.index_num) || [];
      list.push(question);
      byIndex.set(question.index_num, list);
    }

    let matched = 0;
    let ambiguous = 0;
    let unmatched = 0;
    let ignored = 0;
    for (const source of sources) {
      const candidates = byIndex.get(source.question_index) || [];
      if (!candidates.length && this.isSequentialFallbackSource(source)) {
        await this.answerSourceRepository.update(source.id, {
          status: AnswerSourceStatus.Ignored,
          matched_question_id: null,
          match_score: null,
        });
        ignored += 1;
        continue;
      }

      const ranked = this.rankCandidates(source, candidates);
      const top = ranked[0];
      if (top && this.isSequentialFallbackSource(source)) {
        await this.answerSourceRepository.update(source.id, {
          status: AnswerSourceStatus.Ambiguous,
          matched_question_id: top.question.id,
          match_score: top.score,
        });
        ambiguous += 1;
      } else if (top && ranked.length === 1 && top.score >= 85) {
        await this.applySourceToQuestion(source, top.question, top.score);
        await this.answerSourceRepository.update(source.id, {
          status: AnswerSourceStatus.Matched,
          matched_question_id: top.question.id,
          match_score: top.score,
        });
        matched += 1;
      } else if (top && top.score >= 70) {
        await this.answerSourceRepository.update(source.id, {
          status: AnswerSourceStatus.Ambiguous,
          matched_question_id: top.question.id,
          match_score: top.score,
        });
        ambiguous += 1;
      } else {
        await this.answerSourceRepository.update(source.id, {
          status: AnswerSourceStatus.Unmatched,
          matched_question_id: null,
          match_score: null,
        });
        unmatched += 1;
      }
    }
    return {
      total: matched + ambiguous + unmatched,
      matched,
      ambiguous,
      unmatched,
      ignored,
      parsed_total: sources.length,
    };
  }

  private async clearQuestionBindingsForSources(sources: AnswerSource[]) {
    for (const source of sources) {
      await this.questionRepository.update(
        { answer_source_id: source.id },
        {
          answer_source_id: null,
          analysis_match_confidence: null,
          analysis_image_url: null,
        },
      );
    }
  }

  private isSequentialFallbackSource(source: AnswerSource) {
    return (
      source.parse_mode === AnswerSourceParseMode.Image &&
      source.raw_text === 'color_note_block_fallback' &&
      Boolean(source.question_anchor?.startsWith('顺序题块'))
    );
  }

  private isSequentialFallbackCandidate(candidate: Record<string, any>) {
    return (
      candidate.parse_mode === AnswerSourceParseMode.Image &&
      candidate.raw_text === 'color_note_block_fallback' &&
      String(candidate.question_anchor || '').startsWith('顺序题块')
    );
  }

  private rankCandidates(source: AnswerSource, questions: Question[]) {
    return questions
      .map((question) => ({
        question,
        score: this.scoreMatch(source, question, questions.length),
      }))
      .sort((left, right) => right.score - left.score);
  }

  private scoreMatch(source: AnswerSource, question: Question, duplicateCount: number) {
    if (this.isSequentialFallbackSource(source)) {
      return source.question_index === question.index_num ? 60 : 0;
    }

    let score = 0;
    const textEvidence = this.textEvidenceScore(source, question);
    if (source.question_index === question.index_num) score += 45;
    if (source.section_key && this.questionText(question).includes(source.section_key)) {
      score += 10;
    }
    if (source.question_anchor && question.source_anchor_text === source.question_anchor) {
      score += 20;
    }
    score += textEvidence;
    if (source.confidence >= 85) score += 5;
    if (duplicateCount === 1) score += 10;
    if (duplicateCount > 1) score = Math.min(score, 70);
    if (textEvidence < 20 && source.question_anchor !== question.source_anchor_text) {
      score = Math.min(score, 60);
    }
    return Math.max(0, Math.min(100, score));
  }

  private questionText(question: Question) {
    return [question.content, question.raw_text, question.source_anchor_text]
      .filter(Boolean)
      .join('\n');
  }

  private sourceText(source: AnswerSource) {
    return [source.raw_text, source.analysis_text, source.question_anchor, source.section_key]
      .filter(Boolean)
      .join('\n');
  }

  private textEvidenceScore(source: AnswerSource, question: Question) {
    const sourceTokens = this.significantTokens(this.sourceText(source));
    const questionTokens = this.significantTokens(this.questionText(question));
    if (!sourceTokens.size || !questionTokens.size) return 0;

    let overlap = 0;
    for (const token of questionTokens) {
      if (sourceTokens.has(token)) overlap += 1;
    }
    const ratio = overlap / Math.min(questionTokens.size, 30);
    if (overlap >= 10 && ratio >= 0.35) return 35;
    if (overlap >= 6 && ratio >= 0.25) return 25;
    if (overlap >= 3 && ratio >= 0.15) return 15;
    return 0;
  }

  private significantTokens(text: string) {
    const stopWords = new Set([
      '资料分析题库',
      '资料分析',
      '夸夸刷',
      '单位',
      '以下',
      '哪个',
      '范围',
      '的是',
      '约为',
      '比重',
      '同比',
      '增长',
      '亿元',
      '万人',
      '资料',
      '分析',
      '题库',
      'image',
      'chart',
      'visuals',
    ]);
    const normalized = text
      .replace(/[A-D]\s*[.、．]/gi, ' ')
      .replace(/!\[[^\]]*]\([^)]+\)/g, ' ')
      .toLowerCase();
    const rawTokens = normalized.match(/[\u4e00-\u9fa5]+|[a-z0-9]{2,}/g) || [];
    const tokens: string[] = [];
    for (const rawToken of rawTokens) {
      const token = rawToken.trim();
      if (token.length < 2 || stopWords.has(token)) continue;
      tokens.push(token);
      if (/^[\u4e00-\u9fa5]+$/.test(token) && token.length > 2) {
        for (let index = 0; index < token.length - 1; index += 1) {
          tokens.push(token.slice(index, index + 2));
        }
      }
    }
    return new Set(tokens.filter((token) => !stopWords.has(token)));
  }

  private async applySourceToQuestion(
    source: AnswerSource,
    question: Question,
    score: number,
  ) {
    await this.questionRepository.update(question.id, {
      answer: source.answer || question.answer || null,
      analysis: source.analysis_text || question.analysis || null,
      analysis_image_url: source.analysis_image_url || question.analysis_image_url || null,
      answer_source_id: source.id,
      analysis_match_confidence: score,
    });
  }

  private async updateTaskMatchSummary(task: ParseTask, summary: Record<string, any>) {
    await this.taskRepository.update(task.id, {
      status: ParseTaskStatus.Done,
      progress: 100,
      total_count: Number(summary.total || task.total_count || 0),
      done_count: Number(summary.total || task.done_count || 0),
      result_summary: JSON.stringify(summary),
    });
  }

  private resolveErrorMessage(error: unknown) {
    if (axios.isAxiosError(error)) {
      const response = error.response?.data;
      const detail =
        typeof response === 'string'
          ? response
          : response
            ? JSON.stringify(response)
            : error.message;
      return `PDF 服务调用失败: ${detail}`;
    }
    return error instanceof Error ? error.message : '答案册解析失败';
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
      }).filter(([, value]) => Boolean(value)),
    );
  }

  private toNumber(value: unknown, fallback: number) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  private toOptionalNumber(value: unknown) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  private toNumberArray(value: unknown) {
    if (!Array.isArray(value)) return null;
    const numbers = value.map((item) => Number(item)).filter(Number.isFinite);
    return numbers.length ? numbers : null;
  }

  private resolveFileName(url: string) {
    try {
      const pathname = new URL(url).pathname;
      return decodeURIComponent(pathname.split('/').pop() || '');
    } catch {
      return url.split('/').pop() || '';
    }
  }
}
