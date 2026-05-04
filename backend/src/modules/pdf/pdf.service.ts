import {
  BadRequestException,
  Injectable,
  Logger,
  NotFoundException,
} from '@nestjs/common';
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { ConfigService } from '@nestjs/config';
import { InjectRepository } from '@nestjs/typeorm';
import axios from 'axios';
import { EventEmitter } from 'events';
import { Response } from 'express';
import { Repository } from 'typeorm';
import {
  AnswerSource,
  AnswerSourceStatus,
} from '../answer-book/entities/answer-source.entity';
import { BankStatus, QuestionBank } from '../bank/entities/question-bank.entity';
import { Material } from '../question/entities/material.entity';
import {
  SystemConfig,
  SystemConfigValueType,
} from '../system/entities/system-config.entity';
import { UploadService } from '../upload/upload.service';
import {
  Question,
  QuestionReviewStatus,
  QuestionStatus,
  QuestionType,
} from '../question/entities/question.entity';
import { ParsePdfDto } from './dto/parse-pdf.dto';
import { OcrRegionDto, OcrRegionMode } from './dto/ocr-region.dto';
import { PublishResultDto } from './dto/publish-result.dto';
import { QueryParseTaskDto } from './dto/query-parse-task.dto';
import { ParseTask, ParseTaskStatus } from './entities/parse-task.entity';

@Injectable()
export class PdfService {
  private readonly logger = new Logger(PdfService.name);
  private readonly emitter = new EventEmitter();
  private readonly callbackMaterialMaps = new Map<
    string,
    Map<string, Material>
  >();
  private readonly taskQuestionDedupeStats = new Map<
    string,
    {
      duplicated_questions_detected: number;
      duplicated_questions_removed: number;
      duplicate_signature_hits: string[];
    }
  >();
  private readonly taskAiPreauditDebugFiles = new Map<string, string>();
  private readonly activeAbortControllers = new Map<string, AbortController>();

  constructor(
    @InjectRepository(ParseTask)
    private readonly taskRepository: Repository<ParseTask>,
    @InjectRepository(Question)
    private readonly questionRepository: Repository<Question>,
    @InjectRepository(Material)
    private readonly materialRepository: Repository<Material>,
    @InjectRepository(QuestionBank)
    private readonly bankRepository: Repository<QuestionBank>,
    @InjectRepository(SystemConfig)
    private readonly systemConfigRepository: Repository<SystemConfig>,
    @InjectRepository(AnswerSource)
    private readonly answerSourceRepository: Repository<AnswerSource>,
    private readonly configService: ConfigService,
    private readonly uploadService: UploadService,
  ) {
    this.emitter.on('parse', (taskId: string) => {
      void this.processTask(taskId);
    });
  }

  async parse(dto: ParsePdfDto) {
    this.logger.log(
      `Create parse task bank=${dto.bank_id} file=${dto.file_url}`,
    );
    const task = await this.taskRepository.save(
      this.taskRepository.create({
        bank_id: dto.bank_id,
        file_url: dto.file_url,
        file_name: dto.file_name || this.resolveFileName(dto.file_url),
        status: ParseTaskStatus.Pending,
        progress: 0,
      }),
    );

    setImmediate(() => this.emitter.emit('parse', task.id));
    return { task_id: task.id };
  }

  async getTask(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) {
      throw new NotFoundException('解析任务不存在');
    }
    const liveProgress = await this.readTaskLiveProgress(task);

    return {
      status: task.status,
      progress: task.progress,
      total_count: task.total_count,
      done_count: task.done_count,
      result_summary: task.result_summary,
      error: task.error,
      page_progress: liveProgress.page_progress,
      provider_runtime: liveProgress.provider_runtime,
      stale_processing: liveProgress.stale_processing,
    };
  }

  async publishResult(taskId: string, body: PublishResultDto) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) {
      throw new NotFoundException('解析任务不存在');
    }
    if (task.status !== ParseTaskStatus.Done) {
      throw new BadRequestException('只有已完成的解析任务才能发布结果');
    }

    const taskQuestions = await this.questionRepository.find({
      where: { parse_task_id: task.id },
    });
    const publishable = taskQuestions.filter((question) =>
      this.isPublishableParsedQuestion(question),
    );
    const reviewCount = taskQuestions.length - publishable.length;

    if (publishable.length) {
      for (const question of publishable) {
        question.status = QuestionStatus.Published;
        question.review_status = QuestionReviewStatus.Approved;
        question.needs_review = false;
        await this.questionRepository.save(question);
      }
    }

    const totalCount = await this.questionRepository.count({
      where: { bank_id: task.bank_id, status: QuestionStatus.Published },
    });

    const bank = await this.bankRepository.findOne({
      where: { id: task.bank_id },
    });
    if (!bank) {
      throw new NotFoundException('题库不存在');
    }

    bank.total_count = totalCount;
    if (body.publish_bank) {
      bank.status = BankStatus.Published;
    }
    await this.bankRepository.save(bank);

    return {
      task_id: task.id,
      bank_id: task.bank_id,
      published_count: publishable.length,
      review_count: reviewCount,
      skipped_count: reviewCount,
      bank_status: bank.status,
      total_count: totalCount,
    };
  }

  async ocrRegion(dto: OcrRegionDto) {
    if (!dto.task_id && !dto.file_url) {
      throw new BadRequestException('task_id 或 file_url 至少提供一个');
    }
    const task = dto.task_id
      ? await this.taskRepository.findOne({ where: { id: dto.task_id } })
      : null;
    if (dto.task_id && !task) {
      throw new NotFoundException('解析任务不存在');
    }
    if (dto.question_id) {
      const question = await this.questionRepository.findOne({
        where: { id: dto.question_id },
      });
      if (!question) throw new NotFoundException('题目不存在');
      if (task && question.bank_id !== task.bank_id) {
        throw new BadRequestException('题目不属于该解析任务题库');
      }
    }

    const fileUrl = dto.file_url || task?.file_url;
    if (!fileUrl) throw new BadRequestException('缺少 PDF 文件地址');

    const pdfServiceUrl = this.configService.get<string>(
      'PDF_SERVICE_URL',
      'http://localhost:8001',
    );
    const response = await axios.post(
      `${pdfServiceUrl}/ocr-region`,
      {
        pdf_path_or_url: fileUrl,
        page_num: dto.page_num,
        bbox: dto.bbox,
        mode: dto.mode,
        ai_config: await this.getAiConfig(),
      },
      { timeout: 2 * 60 * 1000 },
    );

    const imageBase64 = response.data?.image_base64;
    let imageUrl = response.data?.image_url || null;
    if (imageBase64) {
      const upload = await this.uploadService.uploadBuffer(
        Buffer.from(String(imageBase64), 'base64'),
        {
          filename: `manual-region-q${dto.question_id || 'unknown'}-p${dto.page_num}.png`,
          mimetype: 'image/png',
          prefix: `manual-regions/${task?.id || 'direct'}`,
        },
      );
      imageUrl = upload.url;
    }

    return {
      text: response.data?.text || '',
      options: this.normalizeOptions(response.data?.options),
      image_url: imageUrl,
      page_num: Number(response.data?.page_num || dto.page_num),
      bbox: response.data?.bbox || dto.bbox,
      confidence: Number(response.data?.confidence || 0),
      source: response.data?.source || (dto.mode === OcrRegionMode.Image ? 'manual_crop' : 'unknown'),
      warnings: Array.isArray(response.data?.warnings) ? response.data.warnings : [],
    };
  }

  cropRegion(dto: OcrRegionDto) {
    return this.ocrRegion({ ...dto, mode: OcrRegionMode.Image });
  }

  async addHeaderFooterBlacklist(body: Record<string, unknown>) {
    const incoming = Array.isArray(body.texts)
      ? body.texts
      : typeof body.text === 'string'
        ? [body.text]
        : [];
    const texts = incoming
      .map((text) => String(text || '').trim())
      .filter(Boolean);
    if (!texts.length) {
      throw new BadRequestException('缺少要加入黑名单的文本');
    }
    const key = 'PDF_HEADER_FOOTER_BLACKLIST';
    let config = await this.systemConfigRepository.findOne({ where: { key } });
    const existing = this.parseJsonArray(config?.value);
    const next = [...new Set([...existing, ...texts])];
    if (!config) {
      config = new SystemConfig();
      config.key = key;
      config.description = 'PDF 页眉页脚解析黑名单';
      config.value_type = SystemConfigValueType.Json;
      config.value = JSON.stringify(next);
    } else {
      config.value = JSON.stringify(next);
    }
    await this.systemConfigRepository.save(config);
    return { key, texts: next };
  }

  listTasks(query: QueryParseTaskDto) {
    return this.taskRepository.find({
      where: query.bankId ? { bank_id: query.bankId } : {},
      relations: ['bank'],
      order: { created_at: 'DESC' },
    });
  }

  private normalizeOptions(value: unknown) {
    if (!value || typeof value !== 'object') return undefined;
    const record = value as Record<string, unknown>;
    return Object.fromEntries(
      ['A', 'B', 'C', 'D']
        .map((key) => [key, record[key] || record[key.toLowerCase()] || ''])
        .filter(([, option]) => Boolean(option)),
    );
  }

  async retry(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    if (
      ![ParseTaskStatus.Failed, ParseTaskStatus.Paused, ParseTaskStatus.Canceled].includes(
        task.status as ParseTaskStatus,
      )
    ) {
      throw new BadRequestException('只有失败、已暂停或已取消的任务才能重试');
    }
    await this.taskRepository.update(task.id, {
      status: ParseTaskStatus.Pending,
      progress: 0,
      error: null,
      total_count: 0,
      done_count: 0,
      attempt: task.attempt + 1,
      result_summary: null,
    });
    setImmediate(() => this.emitter.emit('parse', task.id));
    return { task_id: task.id, status: ParseTaskStatus.Pending };
  }

  async pause(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    if (
      ![ParseTaskStatus.Pending, ParseTaskStatus.Processing].includes(
        task.status as ParseTaskStatus,
      )
    ) {
      throw new BadRequestException('只有等待中或解析中的任务才能暂停');
    }

    const controller = this.activeAbortControllers.get(task.id);
    controller?.abort();
    this.callbackMaterialMaps.delete(task.id);
    await this.taskRepository.update(task.id, {
      status: ParseTaskStatus.Paused,
      error: '用户已暂停解析，可稍后重试',
    });
    return { task_id: task.id, status: ParseTaskStatus.Paused };
  }

  async cancel(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    if (
      ![ParseTaskStatus.Pending, ParseTaskStatus.Processing, ParseTaskStatus.Paused].includes(
        task.status as ParseTaskStatus,
      )
    ) {
      throw new BadRequestException('只有等待中、解析中或已暂停的任务才能取消');
    }
    const controller = this.activeAbortControllers.get(task.id);
    controller?.abort();
    this.callbackMaterialMaps.delete(task.id);
    await this.taskRepository.update(task.id, {
      status: ParseTaskStatus.Canceled,
      error: '用户已取消解析，可稍后重试',
    });
    return { task_id: task.id, status: ParseTaskStatus.Canceled };
  }

  async remove(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    if (task.status === ParseTaskStatus.Processing) {
      throw new BadRequestException('正在处理中的任务不能删除');
    }
    await this.taskRepository.delete(task.id);
    return null;
  }

  async proxySourcePdf(taskId: string, res: Response) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    if (!task.file_url) throw new BadRequestException('解析任务没有原始 PDF 地址');

    try {
      const response = await axios.get(task.file_url, {
        responseType: 'stream',
        timeout: 120000,
        headers: { Accept: 'application/pdf' },
      });
      const contentType =
        typeof response.headers['content-type'] === 'string'
          ? response.headers['content-type']
          : 'application/pdf';
      const contentLength =
        typeof response.headers['content-length'] === 'string'
          ? response.headers['content-length']
          : undefined;
      const fileName = encodeURIComponent(task.file_name || 'source.pdf');

      res.setHeader('Content-Type', contentType);
      res.setHeader('Content-Disposition', `inline; filename*=UTF-8''${fileName}`);
      res.setHeader('Cache-Control', 'private, max-age=600');
      if (contentLength) {
        res.setHeader('Content-Length', contentLength);
      }

      await new Promise<void>((resolve, reject) => {
        const stream = response.data as NodeJS.ReadableStream;
        stream.on('error', reject);
        res.on('finish', resolve);
        res.on('close', resolve);
        stream.pipe(res);
      });
    } catch (error) {
      if (res.headersSent) {
        res.destroy(error instanceof Error ? error : undefined);
        return;
      }
      const message = this.resolveErrorMessage(error);
      this.logger.error(`Proxy PDF failed task=${task.id} message=${message}`);
      throw new BadRequestException(`原始 PDF 加载失败: ${message}`);
    }
  }

  async generateDebugArtifacts(taskId: string, body: Record<string, unknown>) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    if (!task.file_url) throw new BadRequestException('解析任务没有原始 PDF 地址');

    const pdfServiceUrl = this.configService.get<string>(
      'PDF_SERVICE_URL',
      'http://localhost:8001',
    );
    const token = this.configService.get<string>('PDF_SERVICE_INTERNAL_TOKEN', '');
    const response = await axios.post(
      `${pdfServiceUrl}/admin/debug-smoke-by-url`,
      {
        url: task.file_url,
        task_id: task.id,
        pages: typeof body.pages === 'string'
          ? body.pages
          : this.configService.get<string>('PDF_DEBUG_SMOKE_PAGES', '1-8'),
        clean_output: Boolean(body.clean_output),
        refresh_cache: Boolean(body.refresh_cache),
        retry_failed_pages_only: Boolean(body.retry_failed_pages_only),
      },
      {
        timeout: 15 * 60 * 1000,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      },
    );

    const metadata = response.data as Record<string, any>;
    const summary = this.parseResultSummary(task.result_summary);
    summary.debug_artifacts = metadata;
    await this.taskRepository.update(task.id, {
      result_summary: JSON.stringify(summary),
    });
    return metadata;
  }

  async getDebugArtifacts(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    const artifacts = this.parseResultSummary(task.result_summary).debug_artifacts;
    if (!artifacts?.run_id) {
      throw new NotFoundException('调试产物不存在');
    }
    return artifacts;
  }

  async getDebugSummary(taskId: string) {
    const artifacts = await this.getDebugArtifacts(taskId);
    const path = this.resolveDebugArtifactPath(artifacts, 'summary.json');
    return this.fetchDebugArtifact(artifacts.run_id, path, 'json').then(
      (artifact) => artifact.data,
    );
  }

  async getDebugReviewManifest(taskId: string, format: 'json' | 'csv') {
    const artifacts = await this.getDebugArtifacts(taskId);
    const key = format === 'csv' ? 'review_manifest_csv' : 'review_manifest_json';
    const fallback = format === 'csv' ? 'review_manifest.csv' : 'review_manifest.json';
    const path = this.resolveDebugArtifactPath(artifacts, artifacts.files?.[key] || fallback);
    return this.fetchDebugArtifact(artifacts.run_id, path, format);
  }

  async getAiPreauditDebug(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    const debugDir = join(process.cwd(), 'debug', 'pdf-ai-preaudit', task.id);
    const readLocalJson = async (name: string) => {
      try {
        return JSON.parse(await readFile(join(debugDir, name), 'utf-8'));
      } catch {
        return null;
      }
    };
    const debugPayload = await readLocalJson('ai-preaudit-debug.json');
    const finalPreviewPayload = await readLocalJson('final-preview-payload.json');
    const aiAuditResults = await readLocalJson('ai-audit-results.json');
    const finalQuestions = await readLocalJson('final-questions.json');
    const pageUnderstanding = await readLocalJson('page-understanding.json');
    const semanticGroups = await readLocalJson('semantic-groups.json');
    const recropPlan = await readLocalJson('recrop-plan.json');
    const stageCounts = await readLocalJson('stage-counts.json');
    const firstFailedStage = await readLocalJson('first-failed-stage.json');
    const fallbackRecovery = await readLocalJson('fallback-recovery.json');
    const questionNumberScan = await readLocalJson('question-number-scan.json');
    const pageUnderstandingRecovered = await readLocalJson('page-understanding-recovered.json');
    const sourceTextSpanReport = await readLocalJson('source-text-span-report.json');
    const materialGroupBindingReport = await readLocalJson('material-group-binding-report.json');
    if (!debugPayload && !finalPreviewPayload && !aiAuditResults) {
      throw new NotFoundException('AI 预审核调试产物不存在');
    }
    const normalizedM4 = this.normalizeM4DebugPayload({
      taskId: task.id,
      debugDir,
      finalPreviewPayload,
      finalQuestions,
      aiAuditResults,
      semanticGroups,
      pageUnderstanding,
      recropPlan,
    });
    return {
      taskId: task.id,
      bankId: task.bank_id,
      status: task.status,
      debug_dir: debugDir,
      qwen_vl_enabled: Boolean(debugPayload?.qwen_vl_enabled),
      qwen_vl_call_count: Number(debugPayload?.qwen_vl_call_count_after || 0),
      final_verdict: debugPayload?.final_verdict || null,
      final_preview_payload:
        normalizedM4.final_preview_payload ||
        finalPreviewPayload ||
        debugPayload?.final_preview_payload ||
        null,
      final_questions: finalQuestions || debugPayload?.final_questions_after_audit || [],
      ai_audit_results:
        normalizedM4.ai_audit_results || aiAuditResults || debugPayload?.ai_audit_results || [],
      m4_ai_preaudit_summary: normalizedM4.m4_ai_preaudit_summary,
      page_understanding: pageUnderstanding || debugPayload?.page_understanding || [],
      semantic_groups: semanticGroups || debugPayload?.semantic_groups || [],
      recrop_plan: recropPlan || debugPayload?.recrop_plan || [],
      stage_counts: stageCounts || debugPayload?.stage_counts || null,
      first_failed_stage: firstFailedStage || debugPayload?.first_failed_stage || null,
      fallback_recovery: fallbackRecovery || debugPayload?.fallback_recovery || null,
      question_number_scan: questionNumberScan || debugPayload?.question_number_scan || null,
      page_understanding_recovered:
        pageUnderstandingRecovered || debugPayload?.page_understanding_recovered || null,
      source_text_span_report: sourceTextSpanReport || debugPayload?.source_text_span_report || null,
      material_group_binding_report:
        materialGroupBindingReport || debugPayload?.material_group_binding_report || null,
      artifact_refs: {
        ai_preaudit_debug: join(debugDir, 'ai-preaudit-debug.json'),
        final_preview_payload: join(debugDir, 'final-preview-payload.json'),
        final_questions: join(debugDir, 'final-questions.json'),
        ai_audit_results: join(debugDir, 'ai-audit-results.json'),
        page_understanding: join(debugDir, 'page-understanding.json'),
        semantic_groups: join(debugDir, 'semantic-groups.json'),
        recrop_plan: join(debugDir, 'recrop-plan.json'),
        stage_counts: join(debugDir, 'stage-counts.json'),
        first_failed_stage: join(debugDir, 'first-failed-stage.json'),
        fallback_recovery: join(debugDir, 'fallback-recovery.json'),
        question_number_scan: join(debugDir, 'question-number-scan.json'),
        page_understanding_recovered: join(debugDir, 'page-understanding-recovered.json'),
        source_text_span_report: join(debugDir, 'source-text-span-report.json'),
        material_group_binding_report: join(debugDir, 'material-group-binding-report.json'),
        m4_ai_audit_results: join(
          process.cwd(),
          'debug',
          'pdf-semantic',
          task.id,
          'ai-audit-results.json',
        ),
        m4_ai_preaudit_summary: join(
          process.cwd(),
          'debug',
          'pdf-semantic',
          task.id,
          'm4-ai-preaudit-summary.json',
        ),
        m4_api_responses: join(
          process.cwd(),
          'debug',
          'pdf-semantic',
          task.id,
          'api-responses.json',
        ),
      },
    };
  }

  async getPaperCandidates(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');

    const debug = await this.getAiPreauditDebug(taskId);
    const m5aAlignmentReport = await this.readM5aAlignmentReport(task.id);
    const m5aAlignmentByQuestionNo = new Map<number, Record<string, any>>();
    this.toArrayOfObjects(m5aAlignmentReport?.items).forEach((item) => {
      const questionNo = this.toOptionalNumber(item.question_no);
      if (questionNo === null) return;
      m5aAlignmentByQuestionNo.set(questionNo, item);
    });
    const finalQuestions = Array.isArray(debug.final_questions)
      ? (debug.final_questions as Array<Record<string, any>>)
      : [];
    const previewQuestions = Array.isArray(debug.final_preview_payload?.questions)
      ? debug.final_preview_payload.questions
      : [];
    const auditResults = Array.isArray(debug.ai_audit_results)
      ? debug.ai_audit_results
      : [];
    const sourceQuestions = await this.questionRepository.find({
      where: { parse_task_id: task.id },
      relations: ['material'],
      order: { index_num: 'ASC', created_at: 'ASC' },
    });
    const historicalQuestions = (
      await this.questionRepository.find({
        order: { created_at: 'DESC' },
      })
    ).filter((question) => question.parse_task_id !== task.id);
    const sourceQuestionsByNo = new Map(
      sourceQuestions.map((question) => [String(question.index_num), question]),
    );
    const finalQuestionsByNo = new Map<string, Record<string, any>>();
    finalQuestions.forEach((question, index) => {
      finalQuestionsByNo.set(
        this.paperCandidateQuestionKey(
          question?.question_no ?? question?.index_num,
          index,
        ),
        question || {},
      );
    });
    const auditsByNo = new Map<string, Record<string, any>>();
    auditResults.forEach((audit, index) => {
      const key = this.paperCandidateQuestionKey(audit?.question_no, index);
      auditsByNo.set(key, audit);
    });
    const answerSources = await this.answerSourceRepository.find({
      where: { bank_id: task.bank_id },
      order: { question_index: 'ASC', created_at: 'ASC' },
    });
    const answerSourcesByIndex = new Map<number, AnswerSource[]>();
    answerSources.forEach((source) => {
      const list = answerSourcesByIndex.get(source.question_index) || [];
      list.push(source);
      answerSourcesByIndex.set(source.question_index, list);
    });
    const reviewState = await this.readReviewState(task.id);
    const pageMaterialContext = await this.buildPageMaterialContext(
      debug.page_understanding,
    );
    const reviewEventsByCandidateId = new Map<string, Array<Record<string, any>>>();
    this.toArrayOfObjects(reviewState.audit_events).forEach((event) => {
      const key = this.safeDisplayText(event.entity_id, '');
      if (!key) return;
      const list = reviewEventsByCandidateId.get(key) || [];
      list.push(event);
      reviewEventsByCandidateId.set(key, list);
    });

    const sequenceDiagnostics = this.paperCandidateQuestionSequenceDiagnostics(previewQuestions);
    const questions = previewQuestions.map((question, index) => {
      const questionNo = question?.question_no ?? null;
      const key = this.paperCandidateQuestionKey(questionNo, index);
      const audit =
        auditsByNo.get(key) ||
        auditResults[index] ||
        {};
      const baseCandidate = this.buildPaperCandidate(
        task,
        {
          ...(finalQuestionsByNo.get(key) || {}),
          ...(question || {}),
        },
        audit || {},
        index,
        debug,
        sequenceDiagnostics,
      );
      const sourceQuestion =
        sourceQuestionsByNo.get(String(questionNo)) || sourceQuestions[index] || null;
      const similarityCandidates = this.findHistoricalSimilarityCandidates({
        task,
        candidate: baseCandidate,
        sourceQuestion,
        historicalQuestions,
      });
      return this.decoratePaperCandidateForM6({
        task,
        candidate: baseCandidate,
        sourceQuestion,
        m5aAlignment:
          questionNo !== null ? m5aAlignmentByQuestionNo.get(Number(questionNo)) || null : null,
        answerSources:
          questionNo !== null ? answerSourcesByIndex.get(Number(questionNo)) || [] : [],
        pageMaterialContext,
        similarityCandidates,
        historicalQuestionCount: historicalQuestions.length,
        reviewDecision:
          reviewState.review_decisions?.[baseCandidate.candidate_id] || {},
        questionEvents:
          reviewEventsByCandidateId.get(String(baseCandidate.candidate_id)) || [],
      });
    });
    const summary = {
      total: questions.length,
      can_add_count: questions.filter((item) => item.can_add_to_paper).length,
      need_manual_fix_count: questions.filter((item) => item.need_manual_fix).length,
      ai_passed_count: questions.filter((item) => item.ai_audit_status === 'passed').length,
      ai_warning_count: questions.filter((item) => item.ai_audit_status === 'warning').length,
      ai_failed_count: questions.filter((item) => item.ai_audit_status === 'failed').length,
    };
    const finalQuestionsCount = Array.isArray(debug.final_questions)
      ? debug.final_questions.length
      : Number(debug.stage_counts?.final_questions_count || 0);
    const outputQuestionsCount = Number(debug.stage_counts?.output_questions_count || finalQuestionsCount || 0);
    const diagnostics = {
      stage_counts: debug.stage_counts || null,
      first_failed_stage: debug.first_failed_stage || null,
      invariants: [
        outputQuestionsCount > 0 && !previewQuestions.length
          ? {
              code: 'backend_preview_drop_all',
              severity: 'error',
              message: 'kernel/output_questions 非空，但 final_preview_payload.questions 为空',
            }
          : null,
        previewQuestions.length > 0 && !questions.length
          ? {
              code: 'backend_paper_candidates_empty',
              severity: 'error',
              message: 'final_preview_payload.questions 非空，但 paper-candidates 为空',
            }
          : null,
        sequenceDiagnostics.missing_question_numbers.length
          ? {
              code: 'question_number_gap',
              severity: 'error',
              message: `候选题题号不连续，缺失题号：${sequenceDiagnostics.missing_question_numbers.join(',')}`,
              observed_question_numbers: sequenceDiagnostics.observed_question_numbers,
              missing_question_numbers: sequenceDiagnostics.missing_question_numbers,
            }
          : null,
      ].filter(Boolean),
    };
    const payload = {
      taskId: task.id,
      bankId: task.bank_id,
      status: task.status,
      m5a_verdict:
        this.firstMeaningfulText(m5aAlignmentReport?.m5a_verdict) ||
        (answerSources.length ? 'M5A_PASS' : 'M5A_BLOCKED_BY_MISSING_ANSWER_BOOK'),
      m5b_verdict: 'M5B_PASS',
      publish_preview: reviewState.publish_preview || null,
      debug_dir: debug.debug_dir,
      provider: this.firstNonEmptyProvider(debug),
      model: this.firstNonEmptyModel(debug),
      summary,
      diagnostics,
      review_audit_events: reviewState.audit_events || [],
      non_blocking_warnings: [
        m5aAlignmentReport || answerSources.length
          ? null
          : '未提供答本/解析本，M5A 当前仅展示 empty-state 与 seeded fixture，不写入正式库',
        historicalQuestions.length
          ? null
          : '历史题库暂为空，M5B 已执行真实检索，但当前暂无可比对题目',
      ].filter(Boolean),
      questions,
      artifact_refs: {
        ...debug.artifact_refs,
        paper_candidate_payload: join(
          process.cwd(),
          'debug',
          'pdf-ai-preaudit',
          task.id,
          'paper-candidate-payload.json',
        ),
        m5_source_documents_discovery: join(
          process.cwd(),
          'debug',
          'm5',
          task.id,
          'source-documents-discovery.json',
        ),
        m5_answer_book_understanding: join(
          process.cwd(),
          'debug',
          'm5',
          task.id,
          'answer-book-understanding.json',
        ),
        m5_answer_analysis_items: join(
          process.cwd(),
          'debug',
          'm5',
          task.id,
          'answer-analysis-items.json',
        ),
        m5_answer_question_alignment: join(
          process.cwd(),
          'debug',
          'm5',
          task.id,
          'answer-question-alignment.json',
        ),
        m5_answer_match_report: join(
          process.cwd(),
          'debug',
          'm5',
          task.id,
          'm5a-answer-match-report.json',
        ),
      },
    };
    await this.writePaperCandidateArtifact(task.id, payload);
    await this.writeM4SemanticArtifacts(task.id, debug, payload);
    return payload;
  }

  async createDraftPaper(body: Record<string, unknown>) {
    const sourceTaskId = String(body.source_task_id || body.taskId || '').trim();
    if (!sourceTaskId) throw new BadRequestException('source_task_id 必填');
    const candidates = await this.getPaperCandidates(sourceTaskId);
    const bodyQuestions = Array.isArray(body.questions)
      ? this.paperDraftQuestionsFromRequestedCandidates(
          body.questions as Array<Record<string, any>>,
          candidates.questions as Array<Record<string, any>>,
        )
      : candidates.questions.filter((item: Record<string, any>) => item.can_add_to_paper);
    const paperId = randomUUID();
    const sections = this.normalizeDraftSections(body.sections, bodyQuestions);
    const questions = this.normalizeDraftQuestions(bodyQuestions, sections[0]?.id || 'section-1');
    const now = new Date().toISOString();
    const paper = {
      paper_id: paperId,
      title: String(body.title || `解析任务 ${sourceTaskId} 制卷草稿`),
      sections,
      questions,
      score: this.sumDraftScore(questions),
      order: Number(body.order || 1),
      source_task_id: sourceTaskId,
      source_bank_id: String(body.source_bank_id || candidates.bankId || ''),
      debug_dir: candidates.debug_dir,
      created_at: now,
      updated_at: now,
    };
    await this.writeDraftPaper(paperId, paper);
    return paper;
  }

  async getDraftPaper(paperId: string) {
    return this.readDraftPaper(paperId);
  }

  async updateDraftPaper(paperId: string, body: Record<string, unknown>) {
    const existing = await this.readDraftPaper(paperId);
    const requestedQuestions = Array.isArray(body.questions)
      ? await this.paperDraftQuestionsFromExistingDraft(
          existing,
          body.questions as Array<Record<string, any>>,
        )
      : existing.questions;
    const sections = this.normalizeDraftSections(body.sections || existing.sections, requestedQuestions);
    const questions = this.normalizeDraftQuestions(
      requestedQuestions,
      sections[0]?.id || 'section-1',
    );
    const next = {
      ...existing,
      title: String(body.title || existing.title),
      sections,
      questions,
      score: this.sumDraftScore(questions),
      updated_at: new Date().toISOString(),
    };
    await this.writeDraftPaper(paperId, next);
    return next;
  }

  async previewDraftPaper(paperId: string) {
    const paper = await this.readDraftPaper(paperId);
    return {
      ...paper,
      preview: {
        title: paper.title,
        total_score: this.sumDraftScore(paper.questions || []),
        section_count: Array.isArray(paper.sections) ? paper.sections.length : 0,
        question_count: Array.isArray(paper.questions) ? paper.questions.length : 0,
        sections: paper.sections || [],
        questions: paper.questions || [],
      },
    };
  }

  async getReviewState(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    return this.readReviewState(task.id);
  }

  async applyReviewAction(
    taskId: string,
    body: Record<string, unknown>,
    actorId?: string,
  ) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');

    const candidates = await this.getPaperCandidates(task.id);
    const candidateId = this.safeDisplayText(body.candidate_id, '');
    const questionNo = this.toOptionalNumber(body.question_no);
    const candidate =
      candidates.questions.find((item: Record<string, any>) =>
        candidateId ? item.candidate_id === candidateId : false,
      ) ||
      candidates.questions.find((item: Record<string, any>) =>
        questionNo !== null ? Number(item.question_no) === questionNo : false,
      );
    if (!candidate) {
      throw new NotFoundException('候选题不存在或不属于当前任务');
    }

    const action = this.safeDisplayText(body.action, '');
    if (!action) throw new BadRequestException('action 必填');
    const reason =
      this.firstMeaningfulText(body.reason, body.note, body.comment) ||
      'managed-mode review action';
    const evidenceIds = this.toStringArray(body.evidence_ids || body.evidenceIds);
    const state = await this.readReviewState(task.id);
    const key = String(candidate.candidate_id);
    const before = this.cloneJson(state.review_decisions[key] || {});
    const next = { ...before };
    const answerValue =
      this.firstMeaningfulText(body.answer, body.value, body.answer_value) || null;
    const analysisValue =
      this.firstMeaningfulText(body.analysis, body.value, body.analysis_value) ||
      null;

    switch (action) {
      case 'accept_match':
        next.answer_book_decision = 'accepted';
        next.decision_status = 'answer_book_accepted';
        break;
      case 'reject_match':
        next.answer_book_decision = 'rejected';
        next.decision_status = 'answer_book_rejected';
        break;
      case 'override_answer':
        if (!answerValue) {
          throw new BadRequestException('override_answer 需要 answer');
        }
        next.answer_override = answerValue;
        next.decision_status = 'answer_overridden';
        break;
      case 'override_analysis':
        if (!analysisValue) {
          throw new BadRequestException('override_analysis 需要 analysis');
        }
        next.analysis_override = analysisValue;
        next.decision_status = 'analysis_overridden';
        break;
      case 'mark_duplicate':
        next.similarity_decision = 'mark_duplicate';
        next.duplicate_status = 'duplicate_marked';
        next.duplicate_cluster_id =
          this.firstMeaningfulText(body.duplicate_cluster_id, body.cluster_id) ||
          key;
        next.canonical_question_id =
          this.firstMeaningfulText(body.canonical_question_id, body.target_question_id) ||
          null;
        next.decision_status = 'duplicate_marked';
        break;
      case 'keep_both':
        next.similarity_decision = 'keep_both';
        next.duplicate_status = 'keep_both';
        next.decision_status = 'keep_both';
        break;
      case 'mark_sibling':
        next.similarity_decision = 'mark_sibling';
        next.duplicate_status = 'sibling';
        next.decision_status = 'sibling_marked';
        break;
      case 'ignore_similarity':
        next.similarity_decision = 'ignore_similarity';
        next.duplicate_status = 'ignored';
        next.decision_status = 'similarity_ignored';
        break;
      case 'quarantine_question':
        next.quarantined = true;
        next.approved_for_publish = false;
        next.decision_status = 'quarantined';
        break;
      case 'approve_for_publish':
        next.approved_for_publish = true;
        next.quarantined = false;
        next.decision_status = 'approved_for_publish';
        break;
      default:
        throw new BadRequestException('不支持的 review action');
    }

    next.updated_at = new Date().toISOString();
    next.last_reason = reason;
    if (evidenceIds.length) {
      next.evidence_ids = evidenceIds;
    }
    state.review_decisions[key] = next;

    const event = {
      id: randomUUID(),
      actor: actorId || 'managed-mode',
      action,
      entity_type: 'paper_candidate',
      entity_id: key,
      question_no: candidate.question_no ?? null,
      before,
      after: this.cloneJson(next),
      reason,
      evidence_ids: evidenceIds,
      created_at: next.updated_at,
    };
    state.audit_events = [...state.audit_events, event].slice(-800);
    const saved = await this.writeReviewState(task.id, state);

    return {
      task_id: task.id,
      candidate_id: key,
      review_decision: saved.review_decisions[key],
      audit_event: event,
      audit_events: saved.audit_events.filter(
        (item: Record<string, any>) => item.entity_id === key,
      ),
    };
  }

  async publishDraftPaperPreview(
    paperId: string,
    body: Record<string, unknown>,
    actorId?: string,
  ) {
    const paper = await this.readDraftPaper(paperId);
    const taskId = this.safeDisplayText(paper.source_task_id, '');
    if (!taskId) {
      throw new BadRequestException('试卷草稿缺少 source_task_id');
    }
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');

    const now = new Date().toISOString();
    const previewQuestions = Array.isArray(paper.questions)
      ? (paper.questions as Array<Record<string, any>>).map((question, index) =>
          this.buildPreviewPaperQuestion(question, index),
        )
      : [];
    const previewPayload = {
      paper_id: paper.paper_id,
      task_id: task.id,
      source_bank_id: paper.source_bank_id || task.bank_id,
      title: paper.title,
      preview_only: true,
      publish_status: 'preview_ready',
      production_published: false,
      question_count: previewQuestions.length,
      debug_dir: paper.debug_dir || null,
      created_at: paper.created_at,
      updated_at: now,
      questions: previewQuestions,
    };
    await mkdir(this.previewPaperRoot(), { recursive: true });
    await this.writePrettyJson(this.previewPaperPath(paper.paper_id), previewPayload);

    const state = await this.readReviewState(task.id);
    const publishPreview = {
      paper_id: paper.paper_id,
      preview_api_path: `/api/preview-papers/${paper.paper_id}`,
      preview_route: `/quiz-preview/${paper.paper_id}`,
      publish_status: 'preview_ready',
      question_count: previewQuestions.length,
      dry_run: Boolean(body.dry_run ?? true),
      production_published: false,
      created_at: now,
    };
    state.publish_preview = publishPreview;
    state.audit_events = [
      ...state.audit_events,
      {
        id: randomUUID(),
        actor: actorId || 'managed-mode',
        action: 'publish_preview',
        entity_type: 'paper_preview',
        entity_id: paper.paper_id,
        before: null,
        after: publishPreview,
        reason: this.firstMeaningfulText(body.reason, 'preview-only publish') ||
          'preview-only publish',
        evidence_ids: this.toStringArray(body.evidence_ids || body.evidenceIds),
        created_at: now,
      },
    ].slice(-800);
    await this.writeReviewState(task.id, state);
    return {
      ...previewPayload,
      ...publishPreview,
    };
  }

  async buildTaskConsistencyPreview(
    taskId: string,
    body: Record<string, unknown>,
    actorId?: string,
  ) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');

    const candidates = await this.getPaperCandidates(task.id);
    const now = new Date().toISOString();
    const paperId = `h5-audit-${task.id}`;
    const previewQuestions = Array.isArray(candidates.questions)
      ? candidates.questions.map((question: Record<string, any>, index: number) =>
          this.buildPreviewPaperQuestion(question, index),
        )
      : [];
    const previewPayload = {
      paper_id: paperId,
      task_id: task.id,
      source_bank_id: task.bank_id,
      title:
        this.firstMeaningfulText(body.title) ||
        `H5 一致性预览 ${task.id}`,
      preview_only: true,
      preview_scope: 'task_consistency_audit',
      publish_status: 'preview_ready',
      production_published: false,
      question_count: previewQuestions.length,
      debug_dir: candidates.debug_dir || null,
      created_at: now,
      updated_at: now,
      questions: previewQuestions,
    };
    await mkdir(this.previewPaperRoot(), { recursive: true });
    await this.writePrettyJson(this.previewPaperPath(paperId), previewPayload);

    const state = await this.readReviewState(task.id);
    const previewMeta = {
      paper_id: paperId,
      preview_api_path: `/api/preview-papers/${paperId}`,
      preview_route: `/quiz-preview/${paperId}`,
      publish_status: 'preview_ready',
      preview_scope: 'task_consistency_audit',
      question_count: previewQuestions.length,
      production_published: false,
      created_at: now,
    };
    state.h5_consistency_preview = previewMeta;
    state.audit_events = [
      ...state.audit_events,
      {
        id: randomUUID(),
        actor: actorId || 'managed-mode',
        action: 'build_h5_consistency_preview',
        entity_type: 'paper_preview',
        entity_id: paperId,
        before: null,
        after: previewMeta,
        reason:
          this.firstMeaningfulText(body.reason, 'build H5 consistency preview') ||
          'build H5 consistency preview',
        evidence_ids: this.toStringArray(body.evidence_ids || body.evidenceIds),
        created_at: now,
      },
    ].slice(-800);
    await this.writeReviewState(task.id, state);
    return {
      ...previewPayload,
      ...previewMeta,
    };
  }

  async getPreviewPaperForH5(paperId: string) {
    return this.readPreviewPaper(paperId);
  }

  async submitPreviewPaperAnswer(
    paperId: string,
    body: Record<string, unknown>,
    userId?: string,
  ) {
    const preview = await this.readPreviewPaper(paperId);
    const questionId = this.safeDisplayText(
      body.question_id || body.candidate_id || body.id,
      '',
    );
    if (!questionId) throw new BadRequestException('question_id 必填');
    const question = Array.isArray(preview.questions)
      ? (preview.questions as Array<Record<string, any>>).find(
          (item) =>
            this.safeDisplayText(item.id || item.candidate_id, '') === questionId,
        )
      : null;
    if (!question) throw new NotFoundException('预发布题目不存在');

    const normalizedUserAnswer = this.normalizeAnswerForPreview(
      this.safeDisplayText(body.user_answer, ''),
    );
    const normalizedAnswer = this.normalizeAnswerForPreview(
      this.safeDisplayText(question.answer, ''),
    );
    const isCorrect = Boolean(
      normalizedAnswer && normalizedUserAnswer && normalizedUserAnswer === normalizedAnswer,
    );
    const now = new Date().toISOString();
    const submitLogPath = join(
      this.m6TaskRoot(String(preview.task_id || 'preview')),
      'preview-submit-log.json',
    );
    const submitLog = ((await this.readJsonIfExists(submitLogPath)) || []) as Array<Record<string, any>>;
    submitLog.push({
      paper_id: preview.paper_id,
      question_id: questionId,
      user_id: userId || null,
      user_answer: normalizedUserAnswer,
      is_correct: isCorrect,
      created_at: now,
    });
    await this.writePrettyJson(submitLogPath, submitLog.slice(-500));

    return {
      is_correct: isCorrect,
      answer: question.answer || null,
      analysis: question.analysis || null,
      answer_unknown_reason: question.answer_unknown_reason || null,
      analysis_unknown_reason: question.analysis_unknown_reason || null,
      analysis_image_url: null,
      analysis_image_urls: [],
      visual_summary: question.visual_summary || null,
      ai_audit_summary: question.ai_audit_summary || null,
    };
  }

  private paperDraftQuestionsFromRequestedCandidates(
    requestedQuestions: Array<Record<string, any>>,
    canonicalCandidates: Array<Record<string, any>>,
  ) {
    const candidatesById = new Map<string, Record<string, any>>();
    const candidatesByQuestionNo = new Map<string, Record<string, any>>();
    const duplicateQuestionNos = new Set<string>();

    canonicalCandidates.forEach((candidate) => {
      const candidateId = this.safeDisplayText(candidate.candidate_id || candidate.id, '');
      if (candidateId) candidatesById.set(candidateId, candidate);
      if (candidate.question_no !== null && candidate.question_no !== undefined) {
        const key = String(candidate.question_no);
        if (candidatesByQuestionNo.has(key)) duplicateQuestionNos.add(key);
        else candidatesByQuestionNo.set(key, candidate);
      }
    });
    duplicateQuestionNos.forEach((key) => candidatesByQuestionNo.delete(key));

    return requestedQuestions.map((requested, index) => {
      const item = requested && typeof requested === 'object' ? requested : {};
      const requestedId = this.safeDisplayText(item.candidate_id || item.id, '');
      const questionNoKey = item.question_no !== null && item.question_no !== undefined
        ? String(item.question_no)
        : '';
      const canonical =
        (requestedId ? candidatesById.get(requestedId) : null) ||
        (questionNoKey ? candidatesByQuestionNo.get(questionNoKey) : null);

      if (!canonical) {
        throw new BadRequestException(`候选题 ${requestedId || questionNoKey || index + 1} 不存在或不属于当前解析任务`);
      }
      if (!this.paperDraftCandidateCanBeAdded(canonical)) {
        throw new BadRequestException(
          `候选题 ${canonical.question_no ?? canonical.candidate_id ?? index + 1} 不可入卷：${
            canonical.missingContextReason || canonical.cannot_add_reason || '缺少可核验 source evidence'
          }`,
        );
      }

      return {
        ...canonical,
        section_id: item.section_id || canonical.section_id,
        score: item.score ?? canonical.score,
        order: item.order ?? canonical.order,
      };
    });
  }

  private async paperDraftQuestionsFromExistingDraft(
    existing: Record<string, any>,
    requestedQuestions: Array<Record<string, any>>,
  ) {
    const sourceTaskId = this.safeDisplayText(existing.source_task_id || existing.taskId, '');
    if (!sourceTaskId) throw new BadRequestException('试卷草稿缺少 source_task_id，无法校验候选题来源');
    const candidates = await this.getPaperCandidates(sourceTaskId);
    return this.paperDraftQuestionsFromRequestedCandidates(
      requestedQuestions,
      candidates.questions as Array<Record<string, any>>,
    );
  }

  private paperDraftCandidateCanBeAdded(candidate: Record<string, any>) {
    const sourcePageRefs = Array.isArray(candidate.source_page_refs) ? candidate.source_page_refs : [];
    const hasSourceEvidence = Boolean(candidate.source_bbox && candidate.source_text_span);
    return Boolean(
      (candidate.can_add_to_paper || candidate.manualForceAddAllowed) &&
        candidate.source_locator_available &&
        sourcePageRefs.length > 0 &&
        hasSourceEvidence,
    );
  }

  private paperCandidateQuestionKey(questionNo: unknown, index: number) {
    return `${questionNo ?? `idx-${index}`}`;
  }

  private paperCandidateQuestionSequenceDiagnostics(questions: Array<Record<string, any>>) {
    const observedQuestionNumbers = Array.from(
      new Set(
        questions
          .map((question) => this.toOptionalNumber(question?.question_no))
          .filter((value): value is number => Number.isInteger(value) && Number(value) > 0),
      ),
    ).sort((left, right) => left - right);
    const missingQuestionNumbers: number[] = [];
    if (observedQuestionNumbers.length > 1) {
      const observed = new Set(observedQuestionNumbers);
      const first = observedQuestionNumbers[0];
      const last = observedQuestionNumbers[observedQuestionNumbers.length - 1];
      for (let questionNo = first; questionNo <= last; questionNo += 1) {
        if (!observed.has(questionNo)) missingQuestionNumbers.push(questionNo);
      }
    }
    return {
      observed_question_numbers: observedQuestionNumbers,
      missing_question_numbers: missingQuestionNumbers,
    };
  }

  private buildPaperCandidate(
    task: ParseTask,
    question: Record<string, any>,
    audit: Record<string, any>,
    index: number,
    debug: Record<string, any>,
    sequenceDiagnostics: Record<string, any>,
  ) {
    const questionNo = question.question_no ?? audit.question_no ?? null;
    const semanticGroup = this.findSemanticGroup(debug.semantic_groups, questionNo, index);
    const semanticOptions = this.optionsFromSemanticGroup(semanticGroup);
    const options = {
      ...semanticOptions,
      ...Object.fromEntries(
        Object.entries(this.normalizeCandidateOptions(question.options)).filter(([, value]) =>
          Boolean(this.safeDisplayText(value, '')),
        ),
      ),
    };
    const riskFlags = Array.from(
      new Set([
        ...this.toStringArray(question.risk_flags),
        ...this.toStringArray(audit.risk_flags),
      ]),
    );
    const stem = this.safeDisplayText(question.stem, '');
    const visualAssets = Array.isArray(question.visual_assets)
      ? question.visual_assets
      : Array.isArray(question.images)
        ? question.images
        : [];
    const sourcePageRefs = this.paperCandidateSourcePageRefs(question, semanticGroup);
    const sourceBbox = this.firstBbox(
      question.source_bbox,
      question.sourceBbox,
      semanticGroup?.stem_group?.bbox,
      semanticGroup?.bbox,
    );
    const sourceTextSpan = this.safeDisplayText(
      question.source_text_span ||
        question.sourceTextSpan ||
        semanticGroup?.source_text_span ||
        semanticGroup?.stem_group?.source_text_span,
      '',
    ) || null;
    const sourceLocatorAvailable = this.paperCandidateSourceLocatorAvailable(
      task,
      sourcePageRefs,
      sourceBbox,
      sourceTextSpan,
    );
    const materialGroupId = this.safeDisplayText(
      question.material_group_id || question.materialGroupId || semanticGroup?.material_group_id,
      '',
    ) || null;
    const materialGroupQuestionIndexes = this.toNumberArray(
      question.material_group_question_indexes ||
        question.materialGroupQuestionIndexes ||
        semanticGroup?.material_group_question_indexes,
    ) || [];
    const materialGroupConfidence = this.toOptionalNumber(
      question.material_group_confidence ??
        question.materialGroupConfidence ??
        semanticGroup?.material_group_confidence,
    );
    const materialGroupReason = this.safeDisplayText(
      question.material_group_reason || question.materialGroupReason || semanticGroup?.material_group_reason,
      '',
    ) || null;
    const sharedMaterial = Boolean(
      question.shared_material ??
        question.sharedMaterial ??
        (materialGroupQuestionIndexes.length > 1),
    );
    let aiStatus = this.safeDisplayText(
      audit.ai_audit_status || question.ai_audit_status,
      'failed',
    );
    const optionMissing = ['A', 'B', 'C', 'D'].filter((label) => !this.safeDisplayText(options[label], ''));
    const stemMissing = !stem || this.containsForbiddenPlaceholder(stem);
    const visualStatus = this.safeDisplayText(question.visual_parse_status, 'unknown');
    const visualRisk = riskFlags.some((flag) => /chart|table|visual|image|图|表/i.test(flag));
    const hasVisualPayload =
      visualAssets.length > 0 ||
      Boolean(question.preview_image_path) ||
      (Array.isArray(question.image_refs) && question.image_refs.length > 0);
    const imageMissing = visualRisk && !hasVisualPayload;
    const missingQuestionNumbers = Array.isArray(sequenceDiagnostics.missing_question_numbers)
      ? (sequenceDiagnostics.missing_question_numbers as number[])
      : [];
    const sequenceGateFailed = missingQuestionNumbers.length > 0;
    const fallbackFailedPages = Array.isArray(debug.fallback_recovery?.pages)
      ? debug.fallback_recovery.pages
          .filter((p: Record<string, any>) => p.failureReason === 'fallback_failed')
          .map((p: Record<string, any>) => p.page)
      : [];
    const questionOnFallbackFailedPage = sourcePageRefs.some((pageNo: number) =>
      fallbackFailedPages.includes(pageNo),
    );
    if (sequenceGateFailed) {
      ['question_number_gap', 'question_boundary_uncertain'].forEach((flag) => {
        if (!riskFlags.includes(flag)) riskFlags.push(flag);
      });
    }
    const sourceReview = this.paperCandidateManualReviewDecision({
      riskFlags,
      stem,
      sourcePageRefs,
      sourceBbox,
      sourceTextSpan,
      sourceLocatorAvailable,
      semanticGroup,
      materialGroupId,
      sharedMaterial,
    });
    sourceReview.riskFlags.forEach((flag) => {
      if (!riskFlags.includes(flag)) riskFlags.push(flag);
    });
    if (
      aiStatus === 'failed' &&
      !stemMissing &&
      !optionMissing.length &&
      hasVisualPayload &&
      this.safeDisplayText(audit.answer_unknown_reason || question.answer_unknown_reason, '') ===
        'vision_ai_failed_or_unstructured_output'
    ) {
      aiStatus = 'warning';
    }
    if (!sourceReview.manualReviewable && aiStatus === 'passed') {
      aiStatus = 'warning';
    }
    const auditFailed = aiStatus === 'failed' || aiStatus === 'skipped';
    const auditWarning = aiStatus === 'warning';
    const needManualFix = Boolean(
      question.need_manual_fix ||
        audit.needs_review ||
        auditFailed ||
        auditWarning ||
        stemMissing ||
        optionMissing.length ||
        imageMissing ||
        sequenceGateFailed ||
        questionOnFallbackFailedPage ||
        riskFlags.includes('need_manual_fix'),
    );
    const cannotReasons = [
      stemMissing ? '题干缺失或包含占位文本' : '',
      optionMissing.length ? `选项缺失: ${optionMissing.join(',')}` : '',
      imageMissing ? '图表题图片或图表预览缺失' : '',
      sequenceGateFailed ? `题号不连续，缺失题号: ${missingQuestionNumbers.join(',')}` : '',
      questionOnFallbackFailedPage ? `页面解析失败(fallback_failed): pages=[${fallbackFailedPages.join(',')}]` : '',
      auditFailed ? `AI 预审核失败: ${this.safeDisplayText(audit.ai_audit_summary, '未给出摘要')}` : '',
      auditWarning && sourceReview.manualReviewable ? 'AI 预审核 warning，需人工核验原卷后才可强制加入' : '',
      !sourceReview.manualReviewable ? sourceReview.missingContextReason : '',
      riskFlags.includes('chart_title_missing_or_unlocalized') ? '图表标题缺失或未定位' : '',
      riskFlags.includes('table_header_missing_or_unlocalized') ? '表头缺失或未定位' : '',
    ].filter(Boolean);
    const m2FailClosed = fallbackFailedPages.length > 0;
    const canAdd = !m2FailClosed && !cannotReasons.length && aiStatus === 'passed' && !needManualFix && sourceReview.manualReviewable;
    const manualForceAddAllowed =
      !m2FailClosed &&
      auditWarning &&
      sourceReview.manualReviewable &&
      !needManualFix &&
      !canAdd &&
      !sequenceGateFailed &&
      !questionOnFallbackFailedPage;

    return {
      candidate_id: `${task.id}:${questionNo ?? index + 1}`,
      question_no: questionNo,
      stem: stem || null,
      options,
      answer_suggestion:
        audit.answer_suggestion ||
        question.answer_suggestion ||
        question.ai_candidate_answer ||
        (question.ai_audit_status === 'passed' ? question.answer : null) ||
        null,
      answer_confidence: audit.answer_confidence ?? question.answer_confidence ?? null,
      answer_unknown_reason:
        audit.answer_unknown_reason ||
        question.answer_unknown_reason ||
        (audit.answer_suggestion ||
        question.answer_suggestion ||
        question.ai_candidate_answer ||
        (question.ai_audit_status === 'passed' ? question.answer : null)
          ? null
          : '模型未给出可验证答案建议'),
      analysis_suggestion:
        audit.analysis_suggestion ||
        question.analysis_suggestion ||
        question.ai_candidate_analysis ||
        (question.ai_audit_status === 'passed' ? question.analysis : null) ||
        null,
      analysis_confidence: audit.analysis_confidence ?? question.analysis_confidence ?? null,
      analysis_unknown_reason:
        audit.analysis_unknown_reason ||
        question.analysis_unknown_reason ||
        (audit.analysis_suggestion ||
        question.analysis_suggestion ||
        question.ai_candidate_analysis ||
        (question.ai_audit_status === 'passed' ? question.analysis : null)
          ? null
          : '模型未给出可验证解析建议'),
      visual_assets: visualAssets,
      preview_image_path: question.preview_image_path || null,
      visual_summary: question.visual_summary || audit.visual_summary || null,
      visual_confidence:
        question.visual_confidence ?? audit.visual_confidence ?? null,
      source_page_refs: sourcePageRefs,
      source_bbox: sourceBbox,
      source_text_span: sourceTextSpan,
      material_group_id: materialGroupId,
      material_group_question_indexes: materialGroupQuestionIndexes,
      material_group_confidence: materialGroupConfidence,
      material_group_reason: materialGroupReason,
      shared_material: sharedMaterial,
      visual_parse_status: visualStatus,
      ai_audit_status: aiStatus,
      ai_audit_verdict: audit.ai_audit_verdict || question.ai_audit_verdict || null,
      ai_audit_summary: audit.ai_audit_summary || question.ai_audit_summary || null,
      ai_reviewed_before_human: Boolean(
        question.ai_reviewed_before_human ?? audit.ai_reviewed_before_human,
      ),
      risk_flags: riskFlags,
      need_manual_fix: needManualFix,
      can_add_to_paper: canAdd,
      cannot_add_reason: canAdd ? null : cannotReasons.join('；') || '未通过自动入卷规则',
      manual_review_status: sourceReview.status,
      manualReviewable: sourceReview.manualReviewable,
      manualForceAddAllowed,
      missingContextReason: sourceReview.manualReviewable ? null : sourceReview.missingContextReason,
      recommendedAction: sourceReview.recommendedAction,
      source_locator_available: sourceLocatorAvailable,
      source_artifacts_refs: {
        ...(question.source_artifacts_refs || {}),
        ...(debug.artifact_refs || {}),
      },
    };
  }

  private async buildPageMaterialContext(pageUnderstanding: unknown) {
    const byPage = new Map<number, Array<Record<string, any>>>();
    if (!Array.isArray(pageUnderstanding)) return byPage;
    for (const item of pageUnderstanding as Array<Record<string, any>>) {
      const pageNo = this.toOptionalNumber(item.page_no ?? item.page_num);
      const rawOutputRef = this.safeDisplayText(item.raw_output_ref, '');
      if (!pageNo || !rawOutputRef) continue;
      const raw = await this.readJsonIfExists(rawOutputRef);
      const materials = Array.isArray(raw?.raw_output?.materials)
        ? raw.raw_output.materials
        : Array.isArray(raw?.parsed_json?.materials)
          ? raw.parsed_json.materials
          : [];
      if (materials.length) {
        byPage.set(
          pageNo,
          materials.map((material: Record<string, any>) => ({ ...material })),
        );
      }
    }
    return byPage;
  }

  private decoratePaperCandidateForM6(input: {
    task: ParseTask;
    candidate: Record<string, any>;
    sourceQuestion: Question | null;
    m5aAlignment: Record<string, any> | null;
    answerSources: AnswerSource[];
    pageMaterialContext: Map<number, Array<Record<string, any>>>;
    similarityCandidates: Array<Record<string, any>>;
    historicalQuestionCount: number;
    reviewDecision: Record<string, any>;
    questionEvents: Array<Record<string, any>>;
  }) {
    const sourceQuestion = input.sourceQuestion;
    const answerBook = this.buildPaperCandidateAnswerBook({
      candidate: input.candidate,
      sourceQuestion,
      m5aAlignment: input.m5aAlignment,
      answerSources: input.answerSources,
      reviewDecision: input.reviewDecision,
    });
    const similarity = this.buildPaperCandidateSimilarity({
      reviewDecision: input.reviewDecision,
      similarityCandidates: input.similarityCandidates,
      historicalQuestionCount: input.historicalQuestionCount,
    });
    const material = this.buildPaperCandidateMaterial({
      candidate: input.candidate,
      sourceQuestion,
      pageMaterialContext: input.pageMaterialContext,
    });
    const finalAnswerSuggestion =
      this.firstMeaningfulText(
        input.reviewDecision.answer_override,
        input.reviewDecision.answer_book_decision === 'accepted'
          ? answerBook.answer_from_answer_book
          : null,
        answerBook.final_answer_suggestion,
        input.reviewDecision.final_answer_suggestion,
        input.candidate.answer_suggestion,
        sourceQuestion?.answer,
      ) || null;
    const finalAnalysisSuggestion =
      this.firstMeaningfulText(
        input.reviewDecision.analysis_override,
        input.reviewDecision.answer_book_decision === 'accepted'
          ? answerBook.analysis_from_answer_book
          : null,
        answerBook.final_analysis_suggestion,
        input.reviewDecision.final_analysis_suggestion,
        input.candidate.analysis_suggestion,
        sourceQuestion?.analysis,
      ) || null;

    return {
      ...input.candidate,
      question_id: sourceQuestion?.id || null,
      answer: sourceQuestion?.answer || null,
      analysis: sourceQuestion?.analysis || null,
      answer_unknown_reason:
        input.candidate.answer_unknown_reason ||
        sourceQuestion?.answer_unknown_reason ||
        null,
      analysis_unknown_reason:
        input.candidate.analysis_unknown_reason ||
        sourceQuestion?.analysis_unknown_reason ||
        null,
      material,
      m5_answer_book: {
        ...answerBook,
        final_answer_suggestion: finalAnswerSuggestion,
        final_analysis_suggestion: finalAnalysisSuggestion,
      },
      m5_similarity: similarity,
      final_answer_suggestion: finalAnswerSuggestion,
      final_analysis_suggestion: finalAnalysisSuggestion,
      answer_override: input.reviewDecision.answer_override || null,
      analysis_override: input.reviewDecision.analysis_override || null,
      approved_for_publish: Boolean(input.reviewDecision.approved_for_publish),
      quarantined: Boolean(input.reviewDecision.quarantined),
      review_decision_status:
        this.firstMeaningfulText(input.reviewDecision.decision_status) || null,
      audit_events: input.questionEvents,
    };
  }

  private buildPaperCandidateMaterial(input: {
    candidate: Record<string, any>;
    sourceQuestion: Question | null;
    pageMaterialContext: Map<number, Array<Record<string, any>>>;
  }) {
    if (input.sourceQuestion?.material?.content) {
      return {
        id: input.sourceQuestion.material.id,
        content: this.cleanParsedText(input.sourceQuestion.material.content),
        images: Array.isArray(input.sourceQuestion.material.images)
          ? input.sourceQuestion.material.images
          : [],
      };
    }
    const groupId = this.safeDisplayText(input.candidate.material_group_id, '');
    if (!groupId) return null;
    const materialTempId = groupId.replace(/^sg_/, '');
    const pageRefs = Array.isArray(input.candidate.source_page_refs)
      ? input.candidate.source_page_refs
      : [];
    for (const page of pageRefs) {
      const materials = input.pageMaterialContext.get(Number(page)) || [];
      const matched = materials.find(
        (item) =>
          this.safeDisplayText(item.temp_id, '') === materialTempId &&
          this.firstMeaningfulText(item.content),
      );
      if (matched) {
        return {
          id: groupId,
          content: this.cleanParsedText(matched.content),
          images: [],
          source_page: Number(page),
          source: 'page_understanding_raw_material',
        };
      }
    }
    return null;
  }

  private buildPaperCandidateAnswerBook(input: {
    candidate: Record<string, any>;
    sourceQuestion: Question | null;
    m5aAlignment: Record<string, any> | null;
    answerSources: AnswerSource[];
    reviewDecision: Record<string, any>;
  }) {
    if (input.m5aAlignment) {
      const status =
        this.firstMeaningfulText(input.m5aAlignment.status, input.m5aAlignment.verdict) ||
        'matched';
      const conflictReason =
        this.firstMeaningfulText(
          input.reviewDecision.answer_book_decision === 'rejected'
            ? '人工拒绝答本候选'
            : null,
          input.m5aAlignment.conflict_reason,
          input.m5aAlignment.unmatched_reason,
        ) || null;
      return {
        verdict: status,
        status,
        empty_state_text:
          status === 'matched'
            ? null
            : this.firstMeaningfulText(
                input.m5aAlignment.unmatched_reason,
                input.m5aAlignment.conflict_reason,
              ) || '真实答本已加载，当前结果需人工复核',
        answer_from_answer_book:
          this.firstMeaningfulText(input.m5aAlignment.answer_from_answer_book) || null,
        analysis_from_answer_book:
          this.firstMeaningfulText(input.m5aAlignment.analysis_from_answer_book) || null,
        final_answer_suggestion:
          this.firstMeaningfulText(input.m5aAlignment.final_answer_suggestion) || null,
        final_analysis_suggestion:
          this.firstMeaningfulText(input.m5aAlignment.final_analysis_suggestion) || null,
        match_confidence:
          this.toOptionalNumber(input.m5aAlignment.match_confidence) ?? null,
        match_method:
          this.firstMeaningfulText(input.m5aAlignment.match_method) || null,
        evidence: this.m5aEvidenceStrings(input.m5aAlignment.evidence),
        evidence_details:
          input.m5aAlignment.evidence &&
          typeof input.m5aAlignment.evidence === 'object'
            ? this.cloneJson(input.m5aAlignment.evidence)
            : null,
        conflict_reason: conflictReason,
        needs_human_review: Boolean(
          input.m5aAlignment.needs_human_review ?? status !== 'matched',
        ),
        fixture_only: false,
        decision_status:
          this.firstMeaningfulText(input.reviewDecision.answer_book_decision) ||
          (status === 'matched' ? 'report_loaded' : 'human_review_needed'),
        matched_answer_item_id:
          this.firstMeaningfulText(input.m5aAlignment.matched_answer_item_id) || null,
        unmatched_reason:
          this.firstMeaningfulText(input.m5aAlignment.unmatched_reason) || null,
        report_source: 'debug_m5_alignment_report',
        candidates: [
          {
            id:
              this.firstMeaningfulText(input.m5aAlignment.matched_answer_item_id) || null,
            status,
            answer:
              this.firstMeaningfulText(input.m5aAlignment.answer_from_answer_book) || null,
            analysis:
              this.firstMeaningfulText(input.m5aAlignment.analysis_from_answer_book) || null,
            match_confidence:
              this.toOptionalNumber(input.m5aAlignment.match_confidence) ?? null,
            source_page_num:
              this.toOptionalNumber(input.m5aAlignment.evidence?.answer_book_page) ?? null,
          },
        ],
      };
    }
    const primarySource = input.answerSources[0] || null;
    const fixtureAnswer =
      !primarySource &&
      (this.firstMeaningfulText(
        input.sourceQuestion?.answer,
        input.candidate.answer,
        input.candidate.answer_suggestion,
      ) ||
        null);
    const fixtureAnalysis =
      !primarySource &&
      (this.firstMeaningfulText(
        input.sourceQuestion?.analysis,
        input.candidate.analysis,
        input.candidate.analysis_suggestion,
      ) ||
        null);
    const fixtureOnly = Boolean(!primarySource && (fixtureAnswer || fixtureAnalysis));
    const verdict = primarySource
      ? primarySource.status === AnswerSourceStatus.Matched
        ? 'matched'
        : primarySource.status === AnswerSourceStatus.Ambiguous
          ? 'ambiguous'
          : 'available'
      : fixtureOnly
        ? 'fixture_only'
        : 'blocked';
    const conflictReason =
      input.reviewDecision.answer_book_decision === 'rejected'
        ? '人工拒绝答本候选'
        : primarySource &&
            input.sourceQuestion?.answer &&
            primarySource.answer &&
            input.sourceQuestion.answer !== primarySource.answer
          ? '答本候选答案与当前题目答案不一致'
          : fixtureOnly
            ? '当前仅提供 seeded fixture，未写入正式答案源'
            : null;
    return {
      verdict,
      empty_state_text: primarySource
        ? null
        : '未提供答本/解析本，暂无答本候选',
      answer_from_answer_book:
        primarySource?.answer || fixtureAnswer || null,
      analysis_from_answer_book:
        primarySource?.analysis_text || fixtureAnalysis || null,
      match_confidence: primarySource?.match_score ?? null,
      match_method: primarySource
        ? primarySource.status === AnswerSourceStatus.Matched
          ? 'answer_source_match'
          : 'answer_source_ambiguous'
        : fixtureOnly
          ? 'seeded_fixture'
          : null,
      evidence: primarySource
        ? [
            this.safeDisplayText(primarySource.source_pdf_url, ''),
            primarySource.source_page_num
              ? `page:${primarySource.source_page_num}`
              : '',
          ].filter(Boolean)
        : fixtureOnly
          ? ['seeded_fixture:not_from_formal_answer_book']
          : [],
      conflict_reason: conflictReason,
      needs_human_review:
        !primarySource ||
        primarySource.status !== AnswerSourceStatus.Matched ||
        Boolean(conflictReason),
      fixture_only: fixtureOnly,
      decision_status:
        this.firstMeaningfulText(input.reviewDecision.answer_book_decision) ||
        'pending',
      candidates: input.answerSources.map((source) => ({
        id: source.id,
        status: source.status,
        answer: source.answer || null,
        analysis: source.analysis_text || null,
        match_confidence: source.match_score ?? null,
        source_page_num: source.source_page_num,
      })),
    };
  }

  private buildPaperCandidateSimilarity(input: {
    reviewDecision: Record<string, any>;
    similarityCandidates: Array<Record<string, any>>;
    historicalQuestionCount: number;
  }) {
    const computedCandidates = input.similarityCandidates;
    const topCandidate = computedCandidates[0] || null;
    const computedDuplicateStatus = topCandidate?.edge_type || 'no_similarity_candidates';
    const computedClusterId =
      topCandidate?.duplicate_cluster_id ||
      (topCandidate?.similarity_signature
        ? `sim_${createHash('sha256')
            .update(String(topCandidate.similarity_signature))
            .digest('hex')
            .slice(0, 12)}`
        : null);
    const emptyStateText = computedCandidates.length
      ? `已检索 ${input.historicalQuestionCount} 道历史题，命中 ${computedCandidates.length} 个相似候选`
      : input.historicalQuestionCount
        ? `已检索 ${input.historicalQuestionCount} 道历史题，未命中相似候选`
        : '历史题库为空，暂无可比对题目';
    return {
      duplicate_status:
        this.firstMeaningfulText(
          input.reviewDecision.duplicate_status,
          computedDuplicateStatus,
        ) || 'no_similarity_candidates',
      duplicate_cluster_id:
        this.firstMeaningfulText(
          input.reviewDecision.duplicate_cluster_id,
          computedClusterId,
        ) || null,
      canonical_question_id:
        this.firstMeaningfulText(
          input.reviewDecision.canonical_question_id,
          topCandidate?.question_id,
        ) || null,
      similarity_candidates: Array.isArray(input.reviewDecision.similarity_candidates)
        ? input.reviewDecision.similarity_candidates
        : computedCandidates,
      edge_type:
        this.firstMeaningfulText(
          input.reviewDecision.edge_type,
          topCandidate?.edge_type,
        ) || null,
      final_similarity_score: this.toOptionalNumber(
        input.reviewDecision.final_similarity_score ??
          topCandidate?.similarity_score,
      ),
      decision_status:
        this.firstMeaningfulText(input.reviewDecision.similarity_decision) ||
        'not_reviewed',
      empty_state_text: emptyStateText,
    };
  }

  private findHistoricalSimilarityCandidates(input: {
    task: ParseTask;
    candidate: Record<string, any>;
    sourceQuestion: Question | null;
    historicalQuestions: Question[];
  }) {
    const candidateStem =
      this.firstMeaningfulText(
        input.candidate.source_text_span,
        input.candidate.stem,
        input.sourceQuestion?.source_text_span,
        input.sourceQuestion?.content,
      ) || '';
    const candidateOptions = this.paperCandidateSimilarityOptions(
      input.candidate,
      input.sourceQuestion,
    );
    const candidateSignature = this.buildQuestionSimilaritySignature({
      stem: candidateStem,
      options: candidateOptions,
    });
    const candidateRiskFlags = this.toStringArray(input.candidate.risk_flags);
    const candidateMaterialDependent = this.isMaterialDependentCandidate(
      candidateStem,
      candidateRiskFlags,
    );

    const matches = input.historicalQuestions
      .filter((question) => question.id !== input.sourceQuestion?.id)
      .map((question) => {
        const historyStem =
          this.firstMeaningfulText(question.source_text_span, question.content) || '';
        const historyOptions = this.paperCandidateSimilarityOptions(question);
        const historySignature = this.buildQuestionSimilaritySignature({
          stem: historyStem,
          options: historyOptions,
        });
        const stemScore = this.textSimilarityScore(candidateStem, historyStem);
        const optionsScore = this.optionsSimilarityScore(
          candidateOptions,
          historyOptions,
        );
        const sourceTextScore = this.textSimilarityScore(
          this.firstMeaningfulText(
            input.candidate.source_text_span,
            input.candidate.stem,
          ) || candidateStem,
          this.firstMeaningfulText(
            question.source_text_span,
            question.content,
          ) || historyStem,
        );
        const similarityScore = Number(
          (
            Math.max(
              sourceTextScore * 0.75 + optionsScore * 0.25,
              stemScore * 0.7 + optionsScore * 0.3,
            )
          ).toFixed(3),
        );
        const edgeType = this.classifyHistoricalSimilarityEdge({
          candidateSignature,
          historySignature,
          similarityScore,
          stemScore,
          optionsScore,
          candidateMaterialDependent,
          historyMaterialDependent: this.isMaterialDependentCandidate(
            historyStem,
            this.toStringArray(question.parse_warnings),
          ),
        });
        if (!edgeType) return null;
        return {
          question_id: question.id,
          bank_id: question.bank_id,
          parse_task_id: question.parse_task_id || null,
          question_no: question.index_num ?? null,
          status: question.status || null,
          review_status: question.review_status || null,
          edge_type: edgeType,
          similarity_score: similarityScore,
          stem_score: Number(stemScore.toFixed(3)),
          options_score: Number(optionsScore.toFixed(3)),
          exact_signature_match: Boolean(
            candidateSignature &&
              historySignature &&
              candidateSignature === historySignature,
          ),
          duplicate_cluster_id:
            candidateSignature && historySignature && candidateSignature === historySignature
              ? `sim_${createHash('sha256')
                  .update(candidateSignature)
                  .digest('hex')
                  .slice(0, 12)}`
              : null,
          similarity_signature: historySignature,
          content: question.content || null,
          source_text_span: question.source_text_span || null,
          answer: question.answer || null,
          analysis: question.analysis || null,
          source_page_refs: this.questionSourcePageRefsFromEntity(question),
          shared_material: Boolean(question.shared_material),
          visual_summary: question.visual_summary || null,
          has_visual_context: Boolean(question.has_visual_context),
        };
      })
      .filter((item) => Boolean(item)) as Array<Record<string, any>>;
    const orderedMatches = matches
      .sort((left, right) => {
        const rankDelta =
          this.similarityEdgeRank(left.edge_type) -
          this.similarityEdgeRank(right.edge_type);
        if (rankDelta !== 0) return rankDelta;
        const scoreDelta =
          Number(right.similarity_score || 0) - Number(left.similarity_score || 0);
        if (scoreDelta !== 0) return scoreDelta;
        return String(left.question_id || '').localeCompare(
          String(right.question_id || ''),
        );
      });

    const deduped: Array<Record<string, any>> = [];
    const seen = new Set<string>();
    for (const item of orderedMatches) {
      const key = this.safeDisplayText(item.question_id, '');
      if (!key || seen.has(key)) continue;
      seen.add(key);
      deduped.push(item);
      if (deduped.length >= 5) break;
    }
    return deduped;
  }

  private paperCandidateSimilarityOptions(
    candidate: Record<string, any>,
    sourceQuestion?: Question | null,
  ) {
    const candidateOptions = this.normalizeCandidateOptions(candidate.options);
    return {
      A:
        this.firstMeaningfulText(
          candidateOptions.A,
          candidate.option_a,
          sourceQuestion?.option_a,
        ) || '',
      B:
        this.firstMeaningfulText(
          candidateOptions.B,
          candidate.option_b,
          sourceQuestion?.option_b,
        ) || '',
      C:
        this.firstMeaningfulText(
          candidateOptions.C,
          candidate.option_c,
          sourceQuestion?.option_c,
        ) || '',
      D:
        this.firstMeaningfulText(
          candidateOptions.D,
          candidate.option_d,
          sourceQuestion?.option_d,
        ) || '',
    };
  }

  private buildQuestionSimilaritySignature(input: {
    stem?: unknown;
    options?: Record<string, unknown>;
  }) {
    const stem = this.normalizeTextForSignature(input.stem);
    const options = ['A', 'B', 'C', 'D'].map((label) =>
      this.normalizeTextForSignature(input.options?.[label]),
    );
    if (!stem && !options.some(Boolean)) return null;
    return JSON.stringify({ stem, options });
  }

  private classifyHistoricalSimilarityEdge(input: {
    candidateSignature: string | null;
    historySignature: string | null;
    similarityScore: number;
    stemScore: number;
    optionsScore: number;
    candidateMaterialDependent: boolean;
    historyMaterialDependent: boolean;
  }) {
    if (
      input.candidateSignature &&
      input.historySignature &&
      input.candidateSignature === input.historySignature
    ) {
      return 'duplicate';
    }
    if (
      input.similarityScore >= 0.93 ||
      (input.stemScore >= 0.96 && input.optionsScore >= 0.5)
    ) {
      return 'near';
    }
    if (
      input.candidateMaterialDependent &&
      input.historyMaterialDependent &&
      input.stemScore >= 0.58
    ) {
      return 'sibling';
    }
    if (input.similarityScore >= 0.6 || input.stemScore >= 0.68) {
      return 'similar';
    }
    return null;
  }

  private similarityEdgeRank(edgeType: unknown) {
    const order = ['duplicate', 'near', 'sibling', 'similar'];
    const index = order.indexOf(this.safeDisplayText(edgeType, ''));
    return index >= 0 ? index : order.length;
  }

  private optionsSimilarityScore(
    left: Record<string, string>,
    right: Record<string, string>,
  ) {
    let compared = 0;
    let matched = 0;
    for (const label of ['A', 'B', 'C', 'D'] as const) {
      const leftText = this.normalizeTextForSignature(left[label]);
      const rightText = this.normalizeTextForSignature(right[label]);
      if (!leftText && !rightText) continue;
      compared += 1;
      if (leftText && rightText && leftText === rightText) matched += 1;
    }
    return compared ? matched / compared : 0;
  }

  private textSimilarityScore(left: unknown, right: unknown) {
    const leftText = this.normalizeTextForSignature(left);
    const rightText = this.normalizeTextForSignature(right);
    if (!leftText || !rightText) return 0;
    if (leftText === rightText) return 1;
    const leftTokens = this.textSimilarityTokens(leftText);
    const rightTokens = this.textSimilarityTokens(rightText);
    if (!leftTokens.size || !rightTokens.size) return 0;
    let overlap = 0;
    leftTokens.forEach((token) => {
      if (rightTokens.has(token)) overlap += 1;
    });
    return (2 * overlap) / (leftTokens.size + rightTokens.size);
  }

  private textSimilarityTokens(value: string) {
    const tokens = new Set<string>();
    if (!value) return tokens;
    if (value.length <= 2) {
      tokens.add(value);
      return tokens;
    }
    for (let index = 0; index < value.length - 1; index += 1) {
      tokens.add(value.slice(index, index + 2));
    }
    return tokens;
  }

  private normalizeM4DebugPayload(input: {
    taskId: string;
    debugDir: string;
    finalPreviewPayload: Record<string, any> | null;
    finalQuestions: unknown;
    aiAuditResults: unknown;
    semanticGroups: unknown;
    pageUnderstanding: unknown;
    recropPlan: unknown;
  }) {
    const previewPayload =
      input.finalPreviewPayload && typeof input.finalPreviewPayload === 'object'
        ? { ...input.finalPreviewPayload }
        : {};
    const previewQuestions = Array.isArray(previewPayload.questions)
      ? (previewPayload.questions as Array<Record<string, any>>)
      : [];
    const finalQuestions = Array.isArray(input.finalQuestions)
      ? (input.finalQuestions as Array<Record<string, any>>)
      : [];
    const auditResults = Array.isArray(input.aiAuditResults)
      ? (input.aiAuditResults as Array<Record<string, any>>)
      : [];
    const semanticGroups = Array.isArray(input.semanticGroups)
      ? (input.semanticGroups as Array<Record<string, any>>)
      : [];
    const pageUnderstanding = Array.isArray(input.pageUnderstanding)
      ? (input.pageUnderstanding as Array<Record<string, any>>)
      : [];

    const previewByKey = new Map<string, Record<string, any>>();
    const finalByKey = new Map<string, Record<string, any>>();
    const auditByKey = new Map<string, Record<string, any>>();
    const orderedKeys: Array<{ key: string; questionNo: unknown; index: number }> = [];
    const seenKeys = new Set<string>();

    const rememberKey = (questionNo: unknown, index: number) => {
      const key = this.paperCandidateQuestionKey(questionNo, index);
      if (seenKeys.has(key)) return key;
      seenKeys.add(key);
      orderedKeys.push({ key, questionNo, index });
      return key;
    };

    previewQuestions.forEach((question, index) => {
      previewByKey.set(rememberKey(question?.question_no, index), question || {});
    });
    finalQuestions.forEach((question, index) => {
      finalByKey.set(rememberKey(question?.question_no, index), question || {});
    });
    auditResults.forEach((audit, index) => {
      auditByKey.set(rememberKey(audit?.question_no, index), audit || {});
    });

    const normalizedQuestions = orderedKeys.map(({ key, questionNo, index }) =>
      this.buildNormalizedM4PreviewQuestion({
        questionNo,
        previewQuestion: previewByKey.get(key) || previewQuestions[index] || {},
        finalQuestion: finalByKey.get(key) || finalQuestions[index] || {},
        audit: auditByKey.get(key) || auditResults[index] || {},
        semanticGroup: this.findSemanticGroup(semanticGroups, questionNo, index),
        pageUnderstanding,
      }),
    );
    const normalizedAudits = normalizedQuestions.map((question, index) =>
      this.buildNormalizedM4AuditRecord(
        question,
        auditByKey.get(this.paperCandidateQuestionKey(question.question_no, index)) ||
          auditResults[index] ||
          {},
      ),
    );

    return {
      final_preview_payload: {
        ...previewPayload,
        questions: normalizedQuestions,
      },
      ai_audit_results: normalizedAudits,
      m4_ai_preaudit_summary: this.buildM4ArtifactSummary(normalizedQuestions),
    };
  }

  private buildNormalizedM4PreviewQuestion(input: {
    questionNo: unknown;
    previewQuestion: Record<string, any>;
    finalQuestion: Record<string, any>;
    audit: Record<string, any>;
    semanticGroup: Record<string, any> | null;
    pageUnderstanding: Array<Record<string, any>>;
  }) {
    const previewQuestion = input.previewQuestion || {};
    const finalQuestion = input.finalQuestion || {};
    const audit = input.audit || {};
    const semanticGroup = input.semanticGroup;
    const questionNo =
      input.questionNo ??
      previewQuestion.question_no ??
      finalQuestion.question_no ??
      audit.question_no ??
      null;
    const mergedSource = { ...finalQuestion, ...previewQuestion };
    const stemText =
      this.firstMeaningfulText(
        previewQuestion.stem,
        finalQuestion.stem,
        finalQuestion.content,
        input.semanticGroup?.stem_group?.text,
      ) || null;
    const options = {
      ...this.optionsFromSemanticGroup(semanticGroup),
      ...this.normalizeCandidateOptions({
        ...(finalQuestion.options || {}),
        A: finalQuestion.option_a,
        B: finalQuestion.option_b,
        C: finalQuestion.option_c,
        D: finalQuestion.option_d,
      }),
      ...this.normalizeCandidateOptions(previewQuestion.options),
    };
    const visualAssets = this.normalizeM4VisualAssets({
      assets:
        (Array.isArray(previewQuestion.visual_assets) && previewQuestion.visual_assets) ||
        (Array.isArray(previewQuestion.images) && previewQuestion.images) ||
        (Array.isArray(finalQuestion.visual_assets) && finalQuestion.visual_assets) ||
        (Array.isArray(finalQuestion.images) && finalQuestion.images) ||
        [],
      questionNo,
      semanticGroup,
      sourcePageRefs: this.paperCandidateSourcePageRefs(mergedSource, semanticGroup),
    });
    const hasMeaningfulVisualAsset = this.paperCandidateHasMeaningfulVisualAsset(
      visualAssets,
      semanticGroup,
    );
    const visualSummary = this.buildNormalizedVisualSummary({
      previewQuestion,
      finalQuestion,
      semanticGroup,
      visualAssets,
      hasMeaningfulVisualAsset,
    });
    const answerSuggestion = this.firstMeaningfulText(
      audit.answer_suggestion,
      previewQuestion.answer_suggestion,
      finalQuestion.answer_suggestion,
      finalQuestion.ai_candidate_answer,
      this.safeDisplayText(
        audit.ai_audit_status ||
          previewQuestion.ai_audit_status ||
          finalQuestion.ai_audit_status,
        'skipped',
      ) === 'passed'
        ? finalQuestion.answer
        : null,
    );
    const analysisSuggestion = this.firstMeaningfulText(
      audit.analysis_suggestion,
      previewQuestion.analysis_suggestion,
      finalQuestion.analysis_suggestion,
      finalQuestion.ai_candidate_analysis,
      this.safeDisplayText(
        audit.ai_audit_status ||
          previewQuestion.ai_audit_status ||
          finalQuestion.ai_audit_status,
        'skipped',
      ) === 'passed'
        ? finalQuestion.analysis
        : null,
    );
    const answerConfidence = this.toOptionalNumber(
      audit.answer_confidence ??
        previewQuestion.answer_confidence ??
        finalQuestion.answer_confidence ??
        finalQuestion.ai_answer_confidence,
    );
    const analysisConfidence = this.toOptionalNumber(
      audit.analysis_confidence ??
        previewQuestion.analysis_confidence ??
        finalQuestion.analysis_confidence ??
        finalQuestion.ai_analysis_confidence,
    );
    const visualConfidenceCandidates = [
      this.toOptionalNumber(previewQuestion.visual_confidence),
      this.toOptionalNumber(finalQuestion.visual_confidence),
      this.toOptionalNumber(audit.visual_confidence),
      ...visualAssets
        .map((asset) => this.toOptionalNumber(asset.visual_confidence))
        .filter((value): value is number => value !== null),
      ...((Array.isArray(semanticGroup?.visual_group?.blocks)
        ? semanticGroup?.visual_group?.blocks
        : []) as Array<Record<string, any>>)
        .map((block) => this.toOptionalNumber(block.confidence))
        .filter((value): value is number => value !== null),
    ].filter((value): value is number => value !== null);
    const visualConfidence = visualConfidenceCandidates.length
      ? Math.max(...visualConfidenceCandidates)
      : null;
    const aiAuditStatus = this.safeDisplayText(
      audit.ai_audit_status ||
        previewQuestion.ai_audit_status ||
        finalQuestion.ai_audit_status,
      'skipped',
    );
    const answerUnknownReason =
      answerSuggestion ||
      this.firstMeaningfulText(
        audit.answer_unknown_reason,
        previewQuestion.answer_unknown_reason,
        finalQuestion.answer_unknown_reason,
      )
        ? this.firstMeaningfulText(
            audit.answer_unknown_reason,
            previewQuestion.answer_unknown_reason,
            finalQuestion.answer_unknown_reason,
          )
        : '模型未给出可验证答案建议';
    const analysisUnknownReason =
      analysisSuggestion ||
      this.firstMeaningfulText(
        audit.analysis_unknown_reason,
        previewQuestion.analysis_unknown_reason,
        finalQuestion.analysis_unknown_reason,
      )
        ? this.firstMeaningfulText(
            audit.analysis_unknown_reason,
            previewQuestion.analysis_unknown_reason,
            finalQuestion.analysis_unknown_reason,
          )
        : '模型未给出可验证解析建议';

    const riskFlags = Array.from(
      new Set(
        [
          ...this.toStringArray(previewQuestion.risk_flags),
          ...this.toStringArray(audit.risk_flags),
          ...this.toStringArray(finalQuestion.ai_risk_flags),
          ...this.toStringArray(finalQuestion.visual_risk_flags),
          ...this.toStringArray(finalQuestion.parse_warnings),
          ...this.toStringArray(previewQuestion.parse_warnings),
          ...this.toStringArray(finalQuestion.question_quality?.risk_flags),
          ...this.toStringArray(finalQuestion.question_quality?.review_reasons),
          ...this.toStringArray(semanticGroup?.risk_flags),
        ].filter(Boolean),
      ),
    );
    if (!hasMeaningfulVisualAsset && !riskFlags.includes('no_visual_context')) {
      riskFlags.push('no_visual_context');
    }
    if (visualSummary === 'visual_summary_missing' && !riskFlags.includes('visual_summary_missing')) {
      riskFlags.push('visual_summary_missing');
    }
    if (aiAuditStatus !== 'passed' && !riskFlags.includes('need_manual_fix')) {
      riskFlags.push('need_manual_fix');
    }
    if (answerConfidence !== null && answerConfidence < 0.75 && !riskFlags.includes('low_ai_answer_confidence')) {
      riskFlags.push('low_ai_answer_confidence');
    }
    if (
      analysisConfidence !== null &&
      analysisConfidence < 0.75 &&
      !riskFlags.includes('low_ai_analysis_confidence')
    ) {
      riskFlags.push('low_ai_analysis_confidence');
    }
    if (visualConfidence !== null && visualConfidence < 0.75 && !riskFlags.includes('low_visual_confidence')) {
      riskFlags.push('low_visual_confidence');
    }

    const sourcePageRefs = this.paperCandidateSourcePageRefs(mergedSource, semanticGroup);
    const sourceBbox = this.firstBbox(
      previewQuestion.source_bbox,
      finalQuestion.source_bbox,
      semanticGroup?.stem_group?.bbox,
      semanticGroup?.bbox,
    );
    const sourceTextSpan =
      this.firstMeaningfulText(
        previewQuestion.source_text_span,
        finalQuestion.source_text_span,
        semanticGroup?.source_text_span,
        semanticGroup?.stem_group?.source_text_span,
      ) || null;
    const materialGroupId =
      this.firstMeaningfulText(
        previewQuestion.material_group_id,
        finalQuestion.material_group_id,
        semanticGroup?.material_group_id,
      ) || null;
    const materialGroupQuestionIndexes =
      this.toNumberArray(
        previewQuestion.material_group_question_indexes ||
          finalQuestion.material_group_question_indexes ||
          semanticGroup?.material_group_question_indexes,
      ) || [];
    const materialGroupConfidence = this.toOptionalNumber(
      previewQuestion.material_group_confidence ??
        finalQuestion.material_group_confidence ??
        semanticGroup?.material_group_confidence,
    );
    const materialGroupReason =
      this.firstMeaningfulText(
        previewQuestion.material_group_reason,
        finalQuestion.material_group_reason,
        semanticGroup?.material_group_reason,
      ) || null;
    const sharedMaterial = Boolean(
      previewQuestion.shared_material ??
        finalQuestion.shared_material ??
        semanticGroup?.shared_material ??
        (materialGroupQuestionIndexes.length > 1),
    );
    const sourceLocatorAvailable = Boolean(sourcePageRefs.length > 0 && sourceBbox && sourceTextSpan);
    const sourceReview = this.paperCandidateManualReviewDecision({
      riskFlags,
      stem: stemText || '',
      sourcePageRefs,
      sourceBbox,
      sourceTextSpan,
      sourceLocatorAvailable,
      semanticGroup,
      materialGroupId,
      sharedMaterial,
    });
    sourceReview.riskFlags.forEach((flag) => {
      if (!riskFlags.includes(flag)) riskFlags.push(flag);
    });
    const previewImagePath =
      this.firstMeaningfulText(
        previewQuestion.preview_image_path,
        finalQuestion.preview_image_path,
        ...visualAssets.map((asset: Record<string, any>) =>
          this.isMeaningfulVisualRole(asset)
            ? this.firstMeaningfulText(asset.url, asset.image_url, asset.src)
            : null,
        ),
      ) ||
      this.firstMeaningfulText(
        ...visualAssets.map((asset: Record<string, any>) =>
          this.firstMeaningfulText(asset.url, asset.image_url, asset.src),
        ),
      );
    const pageRecord =
      input.pageUnderstanding.find((item) => sourcePageRefs.includes(Number(item.page_no || item.page_num))) ||
      null;

    return {
      ...previewQuestion,
      answer: finalQuestion.answer || previewQuestion.answer || null,
      analysis: finalQuestion.analysis || previewQuestion.analysis || null,
      ai_candidate_answer:
        finalQuestion.ai_candidate_answer || previewQuestion.ai_candidate_answer || null,
      ai_candidate_analysis:
        finalQuestion.ai_candidate_analysis || previewQuestion.ai_candidate_analysis || null,
      question_no: questionNo,
      stem: stemText,
      options,
      visual_assets: visualAssets,
      preview_image_path: previewImagePath || null,
      source_page_refs: sourcePageRefs,
      source_bbox: sourceBbox,
      source_text_span: sourceTextSpan,
      material_group_id: materialGroupId,
      material_group_question_indexes: materialGroupQuestionIndexes,
      material_group_confidence: materialGroupConfidence,
      material_group_reason: materialGroupReason,
      shared_material: sharedMaterial,
      visual_summary: visualSummary,
      visual_confidence: visualConfidence,
      visual_parse_status: this.normalizedVisualParseStatus(
        previewQuestion.visual_parse_status || finalQuestion.visual_parse_status,
        hasMeaningfulVisualAsset,
      ),
      answer_suggestion: answerSuggestion,
      answer_confidence: answerConfidence,
      answer_unknown_reason: answerSuggestion ? null : answerUnknownReason,
      analysis_suggestion: analysisSuggestion,
      analysis_confidence: analysisConfidence,
      analysis_unknown_reason: analysisSuggestion ? null : analysisUnknownReason,
      ai_audit_status: aiAuditStatus,
      ai_audit_verdict:
        this.firstMeaningfulText(
          audit.ai_audit_verdict,
          previewQuestion.ai_audit_verdict,
          finalQuestion.ai_audit_verdict,
        ) || this.defaultAuditVerdictForStatus(aiAuditStatus),
      ai_audit_summary:
        this.firstMeaningfulText(
          audit.ai_audit_summary,
          previewQuestion.ai_audit_summary,
          finalQuestion.ai_audit_summary,
        ) ||
        this.defaultAuditSummary({
          aiAuditStatus,
          visualSummary,
          answerSuggestion,
          answerUnknownReason: answerSuggestion ? null : answerUnknownReason,
          analysisSuggestion,
          analysisUnknownReason: analysisSuggestion ? null : analysisUnknownReason,
          riskFlags,
        }),
      ai_reviewed_before_human: Boolean(
        finalQuestion.ai_reviewed_before_human ??
          previewQuestion.ai_reviewed_before_human ??
          audit.ai_reviewed_before_human ??
          true,
      ),
      risk_flags: riskFlags,
      source_artifacts_refs: {
        ...(previewQuestion.source_artifacts_refs || {}),
        ...(pageRecord?.raw_output_ref
          ? { page_understanding_raw_output: pageRecord.raw_output_ref }
          : {}),
      },
    };
  }

  private buildNormalizedM4AuditRecord(
    question: Record<string, any>,
    rawAudit: Record<string, any>,
  ) {
    return {
      ...rawAudit,
      question_no: question.question_no ?? rawAudit.question_no ?? null,
      ai_audit_status: question.ai_audit_status,
      ai_audit_verdict: question.ai_audit_verdict,
      ai_audit_summary: question.ai_audit_summary,
      ai_reviewed_before_human: Boolean(question.ai_reviewed_before_human),
      visual_parse_status: question.visual_parse_status,
      visual_summary: question.visual_summary,
      visual_confidence: question.visual_confidence ?? null,
      answer_suggestion: question.answer_suggestion,
      answer_confidence: question.answer_confidence ?? null,
      answer_unknown_reason: question.answer_unknown_reason,
      analysis_suggestion: question.analysis_suggestion,
      analysis_confidence: question.analysis_confidence ?? null,
      analysis_unknown_reason: question.analysis_unknown_reason,
      risk_flags: this.toStringArray(question.risk_flags),
      image_linkage: Array.isArray(question.visual_assets)
        ? question.visual_assets.map((asset: Record<string, any>) => ({
            asset_id: asset.asset_id || null,
            page: asset.page ?? null,
            bbox: Array.isArray(asset.bbox) ? asset.bbox : null,
            image_role: asset.image_role || null,
            belongs_to_question: Boolean(asset.belongs_to_question),
            linked_by: asset.linked_by || null,
            link_reason: asset.link_reason || null,
            visual_hash: asset.visual_hash || null,
          }))
        : [],
    };
  }

  private normalizeM4VisualAssets(input: {
    assets: Array<Record<string, any> | string>;
    questionNo: unknown;
    semanticGroup: Record<string, any> | null;
    sourcePageRefs: number[];
  }) {
    const semanticVisualBlocks = Array.isArray(input.semanticGroup?.visual_group?.blocks)
      ? (input.semanticGroup?.visual_group?.blocks as Array<Record<string, any>>)
      : [];
    return input.assets.map((asset, index) => {
      const item =
        typeof asset === 'string'
          ? ({ url: asset } as Record<string, any>)
          : { ...(asset || {}) };
      const role = this.safeDisplayText(item.image_role || item.role, 'unknown');
      const meaningfulVisual = this.isMeaningfulVisualRole(item);
      const semanticVisualBlock = meaningfulVisual ? semanticVisualBlocks[0] || null : null;
      const page =
        this.toOptionalNumber(item.page ?? item.page_no ?? semanticVisualBlock?.page_no) ??
        input.sourcePageRefs[0] ??
        null;
      const bbox = this.firstBbox(
        item.bbox,
        item.raw_bbox,
        item.expanded_bbox,
        semanticVisualBlock?.bbox,
      );
      const imageRole =
        role !== 'unknown'
          ? role
          : meaningfulVisual
            ? 'question_visual'
            : 'question_crop';
      const visualSummary =
        this.firstMeaningfulText(
          item.visual_summary,
          item.caption,
          item.ai_desc,
          semanticVisualBlock?.visual_summary,
          meaningfulVisual ? semanticVisualBlock?.text : null,
        ) || null;
      const visualConfidence = this.toOptionalNumber(
        item.visual_confidence ??
          item.assignment_confidence ??
          semanticVisualBlock?.confidence,
      );
      const assetId =
        this.firstMeaningfulText(
        item.asset_id,
        item.assetId,
        item.ref,
        item.url,
        item.image_url,
        item.src,
      ) || `q${input.questionNo || 'unknown'}-asset-${index + 1}`;
      const linkReason =
        this.firstMeaningfulText(
          item.link_reason,
          meaningfulVisual
            ? `语义视觉块与第 ${input.questionNo || '?'} 题材料组绑定`
            : `题干/选项裁切图已绑定到第 ${input.questionNo || '?'} 题`,
        ) || null;
      const hashPayload = JSON.stringify({
        assetId,
        page,
        bbox,
        imageRole,
        visualSummary,
        url: item.url || item.image_url || item.src || null,
      });
      return {
        ...item,
        asset_id: assetId,
        page,
        bbox,
        image_role: imageRole,
        belongs_to_question: Boolean(item.belongs_to_question ?? true),
        linked_question_no: item.linked_question_no ?? input.questionNo ?? null,
        linked_by: item.linked_by || 'm4_normalizer',
        link_reason: linkReason,
        visual_summary: visualSummary,
        visual_confidence: visualConfidence,
        visual_hash: createHash('sha256').update(hashPayload).digest('hex'),
      };
    });
  }

  private paperCandidateHasMeaningfulVisualAsset(
    visualAssets: Array<Record<string, any>>,
    semanticGroup: Record<string, any> | null,
  ) {
    if (visualAssets.some((asset) => this.isMeaningfulVisualRole(asset))) {
      return true;
    }
    return Boolean(
      Array.isArray(semanticGroup?.visual_group?.blocks) &&
        semanticGroup.visual_group.blocks.length > 0,
    );
  }

  private isMeaningfulVisualRole(asset: Record<string, any>) {
    const role = `${asset?.role || ''} ${asset?.image_role || ''}`.toLowerCase();
    return /chart|table|figure|diagram|visual|question_visual|image/.test(role) &&
      !/question_stem|question_options/.test(role);
  }

  private buildNormalizedVisualSummary(input: {
    previewQuestion: Record<string, any>;
    finalQuestion: Record<string, any>;
    semanticGroup: Record<string, any> | null;
    visualAssets: Array<Record<string, any>>;
    hasMeaningfulVisualAsset: boolean;
  }) {
    const direct = this.firstMeaningfulText(
      input.previewQuestion.visual_summary,
      input.finalQuestion.visual_summary,
    );
    if (direct && !this.isGenericVisualSummary(direct)) return direct;

    const assetSummary = this.firstMeaningfulText(
      ...input.visualAssets
        .filter((asset) => this.isMeaningfulVisualRole(asset))
        .map((asset) =>
          this.firstMeaningfulText(
            asset.visual_summary,
            asset.caption,
            asset.ai_desc,
          ),
        ),
    );
    if (assetSummary) return assetSummary;

    const semanticSummary = this.firstMeaningfulText(
      input.semanticGroup?.visual_group?.text,
      ...((Array.isArray(input.semanticGroup?.visual_group?.blocks)
        ? input.semanticGroup?.visual_group?.blocks
        : []) as Array<Record<string, any>>).map((block) =>
        this.firstMeaningfulText(block.visual_summary, block.text),
      ),
      input.semanticGroup?.title_group?.text,
      input.semanticGroup?.table_header_group?.text,
    );
    if (semanticSummary) return semanticSummary;

    return input.hasMeaningfulVisualAsset ? 'visual_summary_missing' : 'no_visual_context';
  }

  private isGenericVisualSummary(value: unknown) {
    const text = this.safeDisplayText(value, '').toLowerCase();
    return ['question stem', 'question options', 'unknown', 'none', 'null'].includes(text);
  }

  private normalizedVisualParseStatus(rawStatus: unknown, hasMeaningfulVisualAsset: boolean) {
    const text = this.safeDisplayText(rawStatus, '').toLowerCase();
    if (['failed', 'partial', 'unavailable'].includes(text)) return text;
    if (!hasMeaningfulVisualAsset) return 'no_visual_context';
    return text || 'success';
  }

  private defaultAuditVerdictForStatus(status: string) {
    if (status === 'passed') return '可通过';
    if (status === 'warning' || status === 'skipped') return '需复核';
    return '不建议入库';
  }

  private defaultAuditSummary(input: {
    aiAuditStatus: string;
    visualSummary: string | null;
    answerSuggestion: string | null;
    answerUnknownReason: string | null;
    analysisSuggestion: string | null;
    analysisUnknownReason: string | null;
    riskFlags: string[];
  }) {
    if (input.aiAuditStatus === 'passed') {
      return '题干、选项和视觉上下文已补齐，可进入人工终审。';
    }
    const firstReason = this.firstMeaningfulText(
      input.answerUnknownReason,
      input.analysisUnknownReason,
      input.visualSummary === 'visual_summary_missing'
        ? '图表摘要缺失'
        : null,
      input.riskFlags[0],
    );
    if (input.aiAuditStatus === 'failed') {
      return `题目存在阻塞问题，当前不建议入库${firstReason ? `：${firstReason}` : ''}。`;
    }
    return `AI 预审核已执行，但仍需人工复核${firstReason ? `：${firstReason}` : ''}。`;
  }

  private buildM4ArtifactSummary(questions: Array<Record<string, any>>) {
    const total = questions.length;
    const imageLinkageComplete = questions.filter((question) => {
      const visualAssets = Array.isArray(question.visual_assets)
        ? (question.visual_assets as Array<Record<string, any>>)
        : [];
      const meaningfulVisualAssets = visualAssets.filter((asset) =>
        this.isMeaningfulVisualRole(asset),
      );
      if (!meaningfulVisualAssets.length) {
        return question.visual_summary === 'no_visual_context';
      }
      return meaningfulVisualAssets.every((asset) =>
        Boolean(
          asset.asset_id &&
            asset.page &&
            Array.isArray(asset.bbox) &&
            asset.bbox.length === 4 &&
            asset.image_role &&
            asset.linked_by &&
            asset.link_reason &&
            asset.visual_hash,
        ),
      );
    }).length;
    return {
      total,
      ai_audit_status_present: questions.filter((question) =>
        Boolean(question.ai_audit_status),
      ).length,
      ai_audit_verdict_present: questions.filter((question) =>
        Boolean(question.ai_audit_verdict),
      ).length,
      ai_audit_summary_present: questions.filter((question) =>
        Boolean(this.firstMeaningfulText(question.ai_audit_summary)),
      ).length,
      answer_suggestion_present: questions.filter((question) =>
        Boolean(question.answer_suggestion),
      ).length,
      answer_unknown_reason_present: questions.filter((question) =>
        Boolean(question.answer_unknown_reason),
      ).length,
      analysis_suggestion_present: questions.filter((question) =>
        Boolean(question.analysis_suggestion),
      ).length,
      analysis_unknown_reason_present: questions.filter((question) =>
        Boolean(question.analysis_unknown_reason),
      ).length,
      risk_flags_present: questions.filter((question) =>
        Array.isArray(question.risk_flags),
      ).length,
      risk_flags_non_empty: questions.filter((question) =>
        Array.isArray(question.risk_flags) && question.risk_flags.length > 0,
      ).length,
      visual_summary_present: questions.filter((question) =>
        Boolean(question.visual_summary),
      ).length,
      visual_parse_status_present: questions.filter((question) =>
        Boolean(question.visual_parse_status),
      ).length,
      ai_reviewed_before_human_true: questions.filter((question) =>
        Boolean(question.ai_reviewed_before_human),
      ).length,
      with_visual_assets: questions.filter((question) => {
        const visualAssets = Array.isArray(question.visual_assets)
          ? (question.visual_assets as Array<Record<string, any>>)
          : [];
        return visualAssets.some((asset) => this.isMeaningfulVisualRole(asset));
      }).length,
      image_linkage_complete: imageLinkageComplete,
    };
  }

  private async writeM4SemanticArtifacts(
    taskId: string,
    debug: Record<string, any>,
    paperCandidatesPayload: Record<string, any>,
  ) {
    const semanticDir = resolve(process.cwd(), 'debug', 'pdf-semantic', taskId);
    await mkdir(semanticDir, { recursive: true });
    const questions = Array.isArray(paperCandidatesPayload.questions)
      ? (paperCandidatesPayload.questions as Array<Record<string, any>>)
      : [];
    const aiAuditResults = questions.map((question) =>
      this.buildNormalizedM4AuditRecord(question, {}),
    );
    const summary = this.buildM4ArtifactSummary(questions);
    await writeFile(
      join(semanticDir, 'ai-audit-results.json'),
      `${JSON.stringify(aiAuditResults, null, 2)}\n`,
      'utf-8',
    );
    await writeFile(
      join(semanticDir, 'm4-ai-preaudit-summary.json'),
      `${JSON.stringify(summary, null, 2)}\n`,
      'utf-8',
    );
    await writeFile(
      join(semanticDir, 'api-responses.json'),
      `${JSON.stringify(
        {
          task_id: taskId,
          generated_at: new Date().toISOString(),
          paper_candidates: paperCandidatesPayload,
          ai_preaudit_debug: {
            taskId: debug.taskId,
            status: debug.status,
            debug_dir: debug.debug_dir,
            artifact_refs: debug.artifact_refs,
            m4_ai_preaudit_summary: summary,
          },
        },
        null,
        2,
      )}\n`,
      'utf-8',
    );
  }

  private firstMeaningfulText(...values: unknown[]) {
    for (const value of values) {
      const text = this.safeDisplayText(value, '');
      if (!text) continue;
      if (this.containsForbiddenPlaceholder(text)) continue;
      if (this.isGenericVisualSummary(text)) continue;
      if (/^(unknown|none|null|n\/a|na)$/i.test(text)) continue;
      return text;
    }
    return null;
  }

  private findSemanticGroup(value: unknown, questionNo: unknown, index: number) {
    const groups = Array.isArray(value) ? (value as Array<Record<string, any>>) : [];
    return (
      groups.find((group) => String(group.question_no ?? '') === String(questionNo ?? '')) ||
      groups[index] ||
      null
    );
  }

  private optionsFromSemanticGroup(group: Record<string, any> | null) {
    const options: Record<string, string> = {};
    const blocks = Array.isArray(group?.options_group?.blocks)
      ? (group?.options_group?.blocks as Array<Record<string, any>>)
      : [];
    for (const block of blocks) {
      const label = String(block.label || '').trim().toUpperCase();
      if (!['A', 'B', 'C', 'D'].includes(label)) continue;
      const text = this.safeDisplayText(block.text, '');
      if (text) options[label] = text;
    }
    return {
      A: options.A || '',
      B: options.B || '',
      C: options.C || '',
      D: options.D || '',
    };
  }

  private firstBbox(...values: unknown[]) {
    for (const value of values) {
      const numbers = this.toNumberArray(value);
      if (numbers?.length === 4) return numbers;
    }
    return null;
  }

  private paperCandidateSourcePageRefs(question: Record<string, any>, semanticGroup: Record<string, any> | null) {
    const direct = this.toNumberArray(
      question.source_page_refs || question.sourcePageRefs || question.page_range || question.pageRange,
    );
    if (direct?.length) return direct;

    const start = this.toOptionalNumber(
      question.source_page_start ??
        question.sourcePageStart ??
        semanticGroup?.source_page_start ??
        semanticGroup?.sourcePageStart ??
        question.page_num ??
        question.page ??
        semanticGroup?.page_num ??
        semanticGroup?.page,
    );
    if (!start || start < 1) return [];
    const end = this.toOptionalNumber(
      question.source_page_end ??
        question.sourcePageEnd ??
        semanticGroup?.source_page_end ??
        semanticGroup?.sourcePageEnd,
    ) || start;
    if (end < start || end - start > 50) return [start];
    return Array.from({ length: end - start + 1 }, (_unused, index) => start + index);
  }

  private paperCandidateSourceLocatorAvailable(
    task: ParseTask,
    sourcePageRefs: unknown[],
    sourceBbox: number[] | null,
    sourceTextSpan: string | null,
  ) {
    return Boolean(
      this.safeDisplayText(task.file_url, '') &&
        sourcePageRefs.length > 0 &&
        sourceBbox &&
        sourceTextSpan,
    );
  }

  private paperCandidateManualReviewDecision(input: {
    riskFlags: string[];
    stem: string;
    sourcePageRefs: unknown[];
    sourceBbox: number[] | null;
    sourceTextSpan: string | null;
    sourceLocatorAvailable: boolean;
    semanticGroup: Record<string, any> | null;
    materialGroupId?: string | null;
    sharedMaterial?: boolean;
  }) {
    const riskText = input.riskFlags.join(' ');
    const materialDependent = this.isMaterialDependentCandidate(input.stem, input.riskFlags);
    const hasMaterialEvidence = Boolean(input.materialGroupId || input.sharedMaterial || this.hasMaterialEvidence(input.semanticGroup));
    const hasSourcePage = input.sourcePageRefs.length > 0;
    const hasSourceEvidence = Boolean(input.sourceBbox || input.sourceTextSpan);
    const hasSourceTextSpan = Boolean(input.sourceTextSpan);
    const sourceLocatorMissing = !input.sourceLocatorAvailable;
    const extraRiskFlags = new Set<string>();

    if (!hasSourcePage) extraRiskFlags.add('source_page_missing');
    if (!hasSourceEvidence || !hasSourceTextSpan) {
      extraRiskFlags.add('source_unverified');
      extraRiskFlags.add('source_evidence_missing');
    }
    if (!input.sourceBbox) extraRiskFlags.add('source_bbox_missing');
    if (!hasSourceTextSpan) extraRiskFlags.add('source_text_span_missing');
    if (sourceLocatorMissing) extraRiskFlags.add('paper_review_original_pdf_locator_missing');

    const missingPreviousPage = /partial_pdf_context|missing_previous_page_context/i.test(riskText);
    const questionNotFound = /question_not_found_in_pdf/i.test(riskText);
    const materialBindingMissing =
      /shared_material_missing|material_group_unbound|material_locator_missing|semantic_visual_incomplete|缺少.*(?:材料|图表|数据)/i.test(
        riskText,
      );
    const sourceUnverified =
      /source_unverified/i.test(riskText) || sourceLocatorMissing || !input.sourceBbox || !hasSourceTextSpan;
    const missingMaterial = materialDependent && (!hasMaterialEvidence || materialBindingMissing);

    if (missingMaterial) {
      extraRiskFlags.add('shared_material_missing');
      extraRiskFlags.add('material_group_unbound');
      extraRiskFlags.add('material_locator_missing');
      extraRiskFlags.add('source_evidence_missing');
      extraRiskFlags.add('semantic_visual_incomplete');
    }
    if (missingPreviousPage) {
      extraRiskFlags.add('partial_pdf_context');
      extraRiskFlags.add('missing_previous_page_context');
    }

    if (missingPreviousPage) {
      return {
        status: 'not_reviewable_missing_previous_page',
        manualReviewable: false,
        missingContextReason:
          '无法人工核验：题干或材料在上一页，当前 PDF 片段缺少上下文，需补齐上一页或使用完整 PDF 重新解析',
        recommendedAction: '补齐上一页重新识别或使用完整 PDF 重新解析',
        riskFlags: Array.from(extraRiskFlags),
      };
    }
    if (questionNotFound) {
      return {
        status: 'not_reviewable_source_unverified',
        manualReviewable: false,
        missingContextReason: '无法人工核验：当前 PDF 中未能可靠定位题目来源，不能确认题目来源',
        recommendedAction: '使用完整 PDF 重新解析',
        riskFlags: Array.from(extraRiskFlags),
      };
    }
    if (missingMaterial) {
      return {
        status: 'not_reviewable_missing_material_group',
        manualReviewable: false,
        missingContextReason: '无法人工核验：资料分析题材料组或图表证据尚未绑定，不能确认共享材料来源',
        recommendedAction: '补齐材料/图表绑定与 locator 后重新识别',
        riskFlags: Array.from(extraRiskFlags),
      };
    }
    if (sourceUnverified) {
      return {
        status: 'not_reviewable_missing_source_context',
        manualReviewable: false,
        missingContextReason: '无法人工核验：缺少原卷定位/source_text_span/source_bbox，不能确认题目来源',
        recommendedAction: '补齐 source evidence 后重新识别',
        riskFlags: Array.from(extraRiskFlags),
      };
    }
    return {
      status: 'reviewable',
      manualReviewable: true,
      missingContextReason: null,
      recommendedAction: '人工核验原卷后处理',
      riskFlags: Array.from(extraRiskFlags),
    };
  }

  private isMaterialDependentCandidate(stem: string, riskFlags: string[]) {
    const text = `${stem} ${riskFlags.join(' ')}`;
    return /(资料|材料|图表|表格|数据|同比|比重|收入|增长额|判断|计算|固定数据|移动数据)/i.test(text);
  }

  private hasMaterialEvidence(group: Record<string, any> | null) {
    if (!group) return false;
    const material = group.material_group || group.shared_material_group || group.shared_material_group_id;
    if (material) return true;
    const visualBlocks = Array.isArray(group.visual_group?.blocks) ? group.visual_group.blocks.length : 0;
    const titleBlocks = Array.isArray(group.title_group?.blocks) ? group.title_group.blocks.length : 0;
    const tableBlocks = Array.isArray(group.table_header_group?.blocks) ? group.table_header_group.blocks.length : 0;
    return visualBlocks > 0 && (titleBlocks > 0 || tableBlocks > 0);
  }

  private normalizeCandidateOptions(value: unknown) {
    const record = value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
    return {
      A: this.safeDisplayText(record.A ?? record.a, ''),
      B: this.safeDisplayText(record.B ?? record.b, ''),
      C: this.safeDisplayText(record.C ?? record.c, ''),
      D: this.safeDisplayText(record.D ?? record.d, ''),
    };
  }

  private safeDisplayText(value: unknown, fallback: string) {
    if (value === null || value === undefined) return fallback;
    if (typeof value === 'string') return value.trim() || fallback;
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    return fallback;
  }

  private firstNonEmptyProvider(debug: Record<string, any>) {
    const rawOutputs = Array.isArray(debug?.ai_preaudit_debug?.qwen_vl_raw_outputs)
      ? debug.ai_preaudit_debug.qwen_vl_raw_outputs
      : [];
    const fromPage = this.firstFromPageUnderstanding(debug.page_understanding, 'provider');
    return fromPage || rawOutputs.find((item: any) => item?.provider)?.provider || null;
  }

  private firstNonEmptyModel(debug: Record<string, any>) {
    const fromPage = this.firstFromPageUnderstanding(debug.page_understanding, 'model');
    return fromPage || null;
  }

  private firstFromPageUnderstanding(value: unknown, key: string) {
    if (!Array.isArray(value)) return null;
    const found = value.find((item) => item && typeof item === 'object' && (item as Record<string, any>)[key]);
    return found ? String((found as Record<string, any>)[key]) : null;
  }

  private async writePaperCandidateArtifact(taskId: string, payload: unknown) {
    const debugDir = join(process.cwd(), 'debug', 'pdf-ai-preaudit', taskId);
    await mkdir(debugDir, { recursive: true });
    await writeFile(
      join(debugDir, 'paper-candidate-payload.json'),
      JSON.stringify(payload, null, 2),
      'utf-8',
    );
  }

  private paperDraftRoot() {
    return join(process.cwd(), 'debug', 'paper-drafts');
  }

  private async readDraftPaper(paperId: string) {
    if (!paperId || paperId.includes('/') || paperId.includes('\\') || paperId.includes('\0')) {
      throw new BadRequestException('非法 paperId');
    }
    try {
      return JSON.parse(await readFile(join(this.paperDraftRoot(), `${paperId}.json`), 'utf-8'));
    } catch {
      throw new NotFoundException('试卷草稿不存在');
    }
  }

  private async writeDraftPaper(paperId: string, paper: Record<string, any>) {
    await mkdir(this.paperDraftRoot(), { recursive: true });
    await writeFile(
      join(this.paperDraftRoot(), `${paperId}.json`),
      JSON.stringify(paper, null, 2),
      'utf-8',
    );
  }

  private m6TaskRoot(taskId: string) {
    return join(process.cwd(), 'debug', 'm6', taskId);
  }

  private reviewStatePath(taskId: string) {
    return join(this.m6TaskRoot(taskId), 'review-state.json');
  }

  private reviewAuditPath(taskId: string) {
    return join(this.m6TaskRoot(taskId), 'review-audit-events.json');
  }

  private previewPaperRoot() {
    return join(process.cwd(), 'debug', 'm6-preview-papers');
  }

  private previewPaperPath(paperId: string) {
    return join(this.previewPaperRoot(), `${paperId}.json`);
  }

  private emptyReviewState(taskId: string) {
    return {
      task_id: taskId,
      updated_at: null,
      m5a_verdict: 'M5A_BLOCKED_BY_MISSING_ANSWER_BOOK',
      m5b_verdict: 'M5B_FAIL',
      review_decisions: {} as Record<string, Record<string, any>>,
      audit_events: [] as Array<Record<string, any>>,
      publish_preview: null as Record<string, any> | null,
    };
  }

  private async readJsonIfExists(path: string) {
    try {
      return JSON.parse(await readFile(path, 'utf-8'));
    } catch {
      return null;
    }
  }

  private async readM5aAlignmentReport(taskId: string) {
    return this.readJsonIfExists(
      join(process.cwd(), 'debug', 'm5', taskId, 'm5a-answer-match-report.json'),
    );
  }

  private m5aEvidenceStrings(evidence: unknown) {
    if (Array.isArray(evidence)) {
      return evidence.map((item) => String(item || '').trim()).filter(Boolean);
    }
    if (!evidence || typeof evidence !== 'object') return [];
    return Object.entries(evidence as Record<string, unknown>)
      .map(([key, value]) => {
        if (value == null || value === '') return '';
        const rendered =
          typeof value === 'string'
            ? value
            : Array.isArray(value)
              ? value.join(',')
              : JSON.stringify(value);
        return `${key}:${rendered}`;
      })
      .filter(Boolean);
  }

  private async writePrettyJson(path: string, payload: unknown) {
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, JSON.stringify(payload, null, 2), 'utf-8');
  }

  private async readReviewState(taskId: string) {
    const fallback = this.emptyReviewState(taskId);
    const loaded = await this.readJsonIfExists(this.reviewStatePath(taskId));
    if (!loaded || typeof loaded !== 'object') return fallback;
    return {
      ...fallback,
      ...loaded,
      task_id: taskId,
      review_decisions:
        loaded.review_decisions && typeof loaded.review_decisions === 'object'
          ? loaded.review_decisions
          : {},
      audit_events: Array.isArray(loaded.audit_events)
        ? loaded.audit_events
        : [],
      publish_preview:
        loaded.publish_preview && typeof loaded.publish_preview === 'object'
          ? loaded.publish_preview
          : null,
    };
  }

  private async writeReviewState(taskId: string, state: Record<string, any>) {
    const next = {
      ...this.emptyReviewState(taskId),
      ...state,
      task_id: taskId,
      updated_at: new Date().toISOString(),
      review_decisions:
        state.review_decisions && typeof state.review_decisions === 'object'
          ? state.review_decisions
          : {},
      audit_events: Array.isArray(state.audit_events) ? state.audit_events : [],
      publish_preview:
        state.publish_preview && typeof state.publish_preview === 'object'
          ? state.publish_preview
          : null,
    };
    await mkdir(this.m6TaskRoot(taskId), { recursive: true });
    await this.writePrettyJson(this.reviewStatePath(taskId), next);
    await this.writePrettyJson(this.reviewAuditPath(taskId), next.audit_events);
    return next;
  }

  private cloneJson<T>(value: T): T {
    return JSON.parse(JSON.stringify(value)) as T;
  }

  private normalizePreviewPaperId(paperId: string) {
    if (
      !paperId ||
      paperId.includes('/') ||
      paperId.includes('\\') ||
      paperId.includes('\0')
    ) {
      throw new BadRequestException('非法 paperId');
    }
    return paperId;
  }

  private async readPreviewPaper(paperId: string) {
    const safePaperId = this.normalizePreviewPaperId(paperId);
    const preview = await this.readJsonIfExists(this.previewPaperPath(safePaperId));
    if (!preview || typeof preview !== 'object') {
      throw new NotFoundException('预发布试卷不存在');
    }
    return preview;
  }

  private normalizeDraftSections(value: unknown, questions: Array<Record<string, any>>) {
    if (Array.isArray(value) && value.length) {
      return value.map((section, index) => {
        const item = section && typeof section === 'object' ? (section as Record<string, any>) : {};
        return {
          id: String(item.id || `section-${index + 1}`),
          title: String(item.title || `第 ${index + 1} 部分`),
          order: Number(item.order || index + 1),
        };
      });
    }
    return [
      {
        id: 'section-1',
        title: questions.length ? '自动候选题' : '待人工修复',
        order: 1,
      },
    ];
  }

  private normalizeDraftQuestions(value: Array<Record<string, any>>, defaultSectionId: string) {
    return value.map((item, index) => ({
      ...item,
      candidate_id: String(item.candidate_id || item.id || `candidate-${index + 1}`),
      id: String(item.question_id || item.id || item.candidate_id || `candidate-${index + 1}`),
      question_no: item.question_no ?? null,
      stem: this.safeDisplayText(item.stem, ''),
      options: this.normalizeCandidateOptions(item.options),
      answer: item.answer || null,
      analysis: item.analysis || null,
      answer_suggestion: item.answer_suggestion || null,
      answer_unknown_reason: item.answer_unknown_reason || null,
      analysis_suggestion: item.analysis_suggestion || null,
      analysis_unknown_reason: item.analysis_unknown_reason || null,
      preview_image_path: item.preview_image_path || null,
      visual_assets: Array.isArray(item.visual_assets) ? item.visual_assets : [],
      material: item.material || null,
      visual_summary: item.visual_summary || null,
      visual_confidence: item.visual_confidence ?? null,
      ai_audit_status: this.safeDisplayText(item.ai_audit_status, 'unknown'),
      ai_audit_verdict: item.ai_audit_verdict || null,
      ai_audit_summary: item.ai_audit_summary || null,
      ai_reviewed_before_human: Boolean(item.ai_reviewed_before_human),
      risk_flags: this.toStringArray(item.risk_flags),
      need_manual_fix: Boolean(item.need_manual_fix),
      can_add_to_paper: Boolean(item.can_add_to_paper),
      cannot_add_reason: item.cannot_add_reason || null,
      manual_review_status: item.manual_review_status || null,
      manualReviewable: Boolean(item.manualReviewable),
      manualForceAddAllowed: Boolean(item.manualForceAddAllowed),
      missingContextReason: item.missingContextReason || null,
      recommendedAction: item.recommendedAction || null,
      m5_answer_book: item.m5_answer_book || null,
      m5_similarity: item.m5_similarity || null,
      final_answer_suggestion: item.final_answer_suggestion || null,
      final_analysis_suggestion: item.final_analysis_suggestion || null,
      answer_override: item.answer_override || null,
      analysis_override: item.analysis_override || null,
      approved_for_publish: Boolean(item.approved_for_publish),
      quarantined: Boolean(item.quarantined),
      review_decision_status: item.review_decision_status || null,
      audit_events: Array.isArray(item.audit_events) ? item.audit_events : [],
      section_id: String(item.section_id || defaultSectionId),
      score: Number(item.score || 1),
      order: Number(item.order || index + 1),
      source_page_refs: Array.isArray(item.source_page_refs) ? item.source_page_refs : [],
    }));
  }

  private buildPreviewPaperQuestion(
    question: Record<string, any>,
    index: number,
  ) {
    const answer =
      this.firstMeaningfulText(
        question.answer_override,
        question.final_answer_suggestion,
        question.answer_suggestion,
        question.answer,
      ) || null;
    const analysis =
      this.firstMeaningfulText(
        question.analysis_override,
        question.final_analysis_suggestion,
        question.analysis_suggestion,
        question.analysis,
      ) || null;
    return {
      id: String(question.id || question.question_id || question.candidate_id || `preview-${index + 1}`),
      candidate_id: String(
        question.candidate_id || question.question_id || question.id || `preview-${index + 1}`,
      ),
      question_no: question.question_no ?? index + 1,
      type: this.safeDisplayText(question.type, 'single') || 'single',
      content: this.safeDisplayText(question.stem, ''),
      option_a: question.options?.A || '',
      option_b: question.options?.B || '',
      option_c: question.options?.C || '',
      option_d: question.options?.D || '',
      answer,
      analysis,
      answer_unknown_reason:
        answer
          ? null
          : this.firstMeaningfulText(
              question.answer_unknown_reason,
              question.m5_answer_book?.empty_state_text,
            ) || '待人工复核：暂无可靠答案',
      analysis_unknown_reason:
        analysis
          ? null
          : this.firstMeaningfulText(question.analysis_unknown_reason) ||
            '待人工复核：暂无可靠解析',
      images: Array.isArray(question.visual_assets)
        ? question.visual_assets.map((asset: Record<string, any>) => ({
            asset_id:
              this.firstMeaningfulText(asset.asset_id, asset.ref, asset.id) ||
              null,
            ref:
              this.firstMeaningfulText(asset.ref, asset.asset_id, asset.id) ||
              null,
            src:
              this.firstMeaningfulText(asset.url, asset.image_url, asset.src) ||
              '',
            url:
              this.firstMeaningfulText(asset.url, asset.image_url, asset.src) ||
              '',
            caption:
              this.firstMeaningfulText(
                asset.visual_summary,
                asset.caption,
                asset.ai_desc,
              ) || null,
            role:
              this.safeDisplayText(asset.image_role || asset.role, 'question_visual') ||
              'question_visual',
            image_role:
              this.safeDisplayText(asset.image_role || asset.role, 'question_visual') ||
              'question_visual',
            visual_hash:
              this.firstMeaningfulText(asset.visual_hash) || null,
          }))
        : [],
      material:
        question.material && typeof question.material === 'object'
          ? question.material
          : null,
      visual_summary: question.visual_summary || null,
      visual_confidence: question.visual_confidence ?? null,
      ai_audit_status: question.ai_audit_status || null,
      ai_audit_verdict: question.ai_audit_verdict || null,
      ai_audit_summary: question.ai_audit_summary || null,
      ai_reviewed_before_human: Boolean(question.ai_reviewed_before_human),
      risk_flags: this.toStringArray(question.risk_flags),
      review_decision_status: question.review_decision_status || null,
      approved_for_publish: Boolean(question.approved_for_publish),
      source_page_refs: Array.isArray(question.source_page_refs)
        ? question.source_page_refs
        : [],
    };
  }

  private normalizeAnswerForPreview(value: string) {
    return String(value || '')
      .trim()
      .replace(/[（）()]/g, '')
      .replace(/\s+/g, '')
      .toUpperCase();
  }

  private sumDraftScore(questions: Array<Record<string, any>>) {
    return questions.reduce((sum, question) => sum + Number(question.score || 0), 0);
  }

  async getDebugArtifact(taskId: string, path: string) {
    const artifacts = await this.getDebugArtifacts(taskId);
    const safePath = this.resolveDebugArtifactPath(artifacts, path);
    return this.fetchDebugArtifact(artifacts.run_id, safePath, 'binary');
  }

  private parseResultSummary(value?: string | null): Record<string, any> {
    if (!value) return {};
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
      return {};
    }
  }

  private mergeTaskResultSummary(
    value: string | null | undefined,
    patch: Record<string, any>,
  ) {
    return {
      ...this.parseResultSummary(value),
      ...patch,
    };
  }

  private kernelRunDebugDir(taskId: string) {
    return join(process.cwd(), 'debug', 'pdf-ai-preaudit', taskId, 'kernel-run');
  }

  private checkpointManifestPath(taskId: string) {
    return join(this.kernelRunDebugDir(taskId), 'debug', 'checkpoint-manifest.json');
  }

  private buildTaskRuntimeSnapshot(
    taskId: string,
    aiConfig: Record<string, string>,
    debugDir: string,
  ) {
    return {
      task_id: taskId,
      debug_dir: debugDir,
      requested_provider_order: this.firstMeaningfulText(
        aiConfig.vision_ai_provider_order,
      ) || null,
      requested_visual_model: this.firstMeaningfulText(aiConfig.visual_model) || null,
      requested_ark_model: this.firstMeaningfulText(aiConfig.ark_vision_model) || null,
      requested_mimo_model: this.firstMeaningfulText(aiConfig.mimo_vision_model) || null,
      started_at: new Date().toISOString(),
    };
  }

  private async readTaskLiveProgress(task: ParseTask) {
    const summary = this.parseResultSummary(task.result_summary);
    const runtime = summary.runtime && typeof summary.runtime === 'object'
      ? summary.runtime
      : null;
    const manifest = await this.readJsonIfExists(this.checkpointManifestPath(task.id));
    const totalPages = Number(
      manifest?.total_pages ||
      summary?.stats?.pages_count ||
      summary?.stage_counts?.pages_count ||
      0,
    );
    const pageEntries =
      manifest?.pages && typeof manifest.pages === 'object'
        ? (manifest.pages as Record<string, Record<string, any>>)
        : {};
    const staleProcessing =
      task.status === ParseTaskStatus.Processing &&
      !this.activeAbortControllers.has(task.id);
    const pages = Array.from({ length: Math.max(0, totalPages) }, (_unused, index) => {
      const pageNo = index + 1;
      const entry = pageEntries[String(pageNo)] || {};
      const rawStatus = this.safeDisplayText(entry.status, '');
      const mappedStatus =
        rawStatus === 'running'
          ? 'processing'
          : rawStatus === 'success'
            ? 'success'
            : rawStatus === 'failed' || rawStatus === 'quarantined'
              ? [ParseTaskStatus.Paused, ParseTaskStatus.Failed, ParseTaskStatus.Canceled].includes(
                  task.status as ParseTaskStatus,
                )
                ? 'retryable'
                : 'failed'
              : 'pending';
      return {
        page_no: pageNo,
        status: mappedStatus,
        stage: this.safeDisplayText(entry.stage, '') || null,
        provider: this.safeDisplayText(entry.provider_used, '') || null,
        attempts: Number(entry.attempts || 0),
        started_at: this.firstMeaningfulText(entry.started_at) || null,
        finished_at: this.firstMeaningfulText(entry.finished_at) || null,
        updated_at: this.firstMeaningfulText(entry.updated_at) || null,
        last_error_type: this.firstMeaningfulText(entry.last_error_type) || null,
        last_error_message: this.firstMeaningfulText(entry.last_error_message) || null,
        recovered_from_cache: Boolean(entry.recovered_from_cache),
      };
    });
    return {
      page_progress: {
        total_pages: totalPages,
        pending_pages: pages.filter((item) => item.status === 'pending').length,
        processing_pages: pages.filter((item) => item.status === 'processing').length,
        success_pages: pages.filter((item) => item.status === 'success').length,
        failed_pages: pages.filter((item) => item.status === 'failed').length,
        retryable_pages: pages.filter((item) => item.status === 'retryable').length,
        manifest_updated_at: this.firstMeaningfulText(manifest?.updated_at) || null,
        pages,
      },
      provider_runtime: {
        ...(runtime || {}),
        service_provider_order_snapshot:
          this.firstMeaningfulText(runtime?.requested_provider_order) || null,
      },
      stale_processing: staleProcessing,
    };
  }

  private resolveDebugArtifactPath(artifacts: Record<string, any>, path: unknown) {
    if (typeof path !== 'string' || !path || path.includes('\0')) {
      throw new BadRequestException('非法 artifact path');
    }
    if (path.startsWith('/') || path.includes('..') || path.includes('\\')) {
      throw new BadRequestException('非法 artifact path');
    }
    const files = artifacts.files && typeof artifacts.files === 'object'
      ? Object.values(artifacts.files as Record<string, unknown>)
      : [];
    const isListedFile = files.includes(path);
    const allowedPrefixes = ['debug/overlays/', 'debug/crops/', 'page_screenshots/'];
    if (!isListedFile && !allowedPrefixes.some((prefix) => path.startsWith(prefix))) {
      throw new BadRequestException('artifact path 不在允许范围内');
    }
    return path;
  }

  private async fetchDebugArtifact(
    runId: string,
    path: string,
    mode: 'json' | 'csv' | 'binary',
  ) {
    const pdfServiceUrl = this.configService.get<string>(
      'PDF_SERVICE_URL',
      'http://localhost:8001',
    );
    const token = this.configService.get<string>('PDF_SERVICE_INTERNAL_TOKEN', '');
    const response = await axios.get(
      `${pdfServiceUrl}/admin/debug-artifacts/${encodeURIComponent(runId)}`,
      {
        params: { path },
        responseType: mode === 'json' ? 'json' : 'arraybuffer',
        timeout: 60 * 1000,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      },
    );
    return {
      data: response.data,
      contentType:
        String(response.headers?.['content-type'] || '') ||
        (mode === 'csv' ? 'text/csv; charset=utf-8' : 'application/octet-stream'),
      contentLength: String(response.headers?.['content-length'] || ''),
    };
  }

  private async processTask(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) {
      return;
    }
    if (task.status !== ParseTaskStatus.Pending) {
      return;
    }

    try {
      this.logger.log(`Start parse task id=${task.id} bank=${task.bank_id}`);
      const debugDir = this.kernelRunDebugDir(task.id);
      const aiConfig = await this.getAiConfig(task.id);
      const runtimeSnapshot = this.buildTaskRuntimeSnapshot(task.id, aiConfig, debugDir);
      await this.taskRepository.update(task.id, {
        status: ParseTaskStatus.Processing,
        progress: 10,
        result_summary: JSON.stringify(
          this.mergeTaskResultSummary(task.result_summary, {
            runtime: runtimeSnapshot,
            debug_dir: debugDir,
          }),
        ),
      });
      await this.clearPreviousTaskResults(task.id);
      this.callbackMaterialMaps.delete(task.id);

      const pdfServiceUrl = this.configService.get<string>(
        'PDF_SERVICE_URL',
        'http://localhost:8001',
      );
      await axios.get(`${pdfServiceUrl}/health`, { timeout: 3000 });
      const backendUrl = this.configService.get<string>(
        'BACKEND_URL',
        'http://localhost:3010',
      );
      const internalToken = this.configService.get<string>(
        'PDF_SERVICE_INTERNAL_TOKEN',
        '',
      );
      const abortController = new AbortController();
      this.activeAbortControllers.set(task.id, abortController);
      const response = await axios.post(
        `${pdfServiceUrl}/parse-by-url`,
        {
          url: task.file_url,
          ai_config: aiConfig,
          debug_dir: debugDir,
          callback_url: `${backendUrl}/internal/pdf/tasks/${task.id}`,
          callback_token: internalToken,
          callback_batch_size: 20,
        },
        { timeout: 30 * 60 * 1000, signal: abortController.signal },
      );

      const result = response.data;
      if (!result?.callback_delivered) {
        if (this.isZeroQuestionParse(result, result.questions || [])) {
          await this.writeAiPreauditDebugArtifacts(task, {
            source: 'direct_response',
            pageCount: Number(result?.stats?.pages_count || 0),
            stats: result.stats || {},
            detection: result.detection || result.stats?.detection || null,
            warnings: result.warnings || result.stats?.warnings || [],
            error: result.error || '未解析到题目',
          });
          await this.markTaskZeroQuestionFailure(task.id, {
            stats: result.stats || {},
            detection: result.detection || result.stats?.detection || null,
            delivery: 'direct_response',
            warnings: result.warnings || result.stats?.warnings || [],
            error: result.error || '未解析到题目',
          });
          await this.refreshBankTotal(task.bank_id);
          this.logger.error(`Failed parse task id=${task.id} reason=zero_questions_extracted`);
          return;
        }
        const materials = await this.saveMaterials(
          task.bank_id,
          result.materials || [],
          task.id,
        );
        const questions = await this.saveQuestions(
          task.id,
          task.bank_id,
          result.questions || [],
          materials,
        );
        if (!questions.length) {
          await this.writeAiPreauditDebugArtifacts(task, {
            source: 'direct_response_after_save',
            pageCount: Number(result?.stats?.pages_count || 0),
            stats: result.stats || {},
            detection: result.detection || result.stats?.detection || null,
            warnings: result.warnings || result.stats?.warnings || [],
            error: '未解析到题目',
            savedCount: 0,
          });
          await this.markTaskZeroQuestionFailure(task.id, {
            stats: result.stats || {},
            detection: result.detection || result.stats?.detection || null,
            delivery: 'direct_response_after_save',
            warnings: result.warnings || result.stats?.warnings || [],
            error: '未解析到题目',
          });
          await this.refreshBankTotal(task.bank_id);
          this.logger.error(`Failed parse task id=${task.id} reason=zero_questions_saved`);
          return;
        }

        await this.taskRepository.update(task.id, {
          status: ParseTaskStatus.Done,
          progress: 100,
          total_count: questions.length,
          done_count: questions.length,
          error: null,
          result_summary: JSON.stringify(
            this.mergeTaskResultSummary(task.result_summary, {
              runtime: runtimeSnapshot,
              debug_dir: debugDir,
              stats: result.stats || {},
              detection: result.detection || result.stats?.detection || null,
              delivery: 'direct_response',
              debug_file: this.taskAiPreauditDebugFiles.get(task.id) || null,
              dedupe: this.taskQuestionDedupeStats.get(task.id) || null,
            }),
          ),
        });
        await this.writeAiPreauditDebugArtifacts(task, {
          source: 'direct_response_done',
          pageCount: Number(result?.stats?.pages_count || 0),
          stats: result.stats || {},
          detection: result.detection || result.stats?.detection || null,
          warnings: result.warnings || result.stats?.warnings || [],
          finalQuestions: questions,
        });
        await this.refreshBankTotal(task.bank_id);
        this.logger.log(
          `Done parse task id=${task.id} questions=${questions.length}`,
        );
      } else {
        const savedCount = await this.questionRepository.count({
          where: { parse_task_id: task.id },
        });
        const finalQuestions = await this.questionRepository.find({
          where: { parse_task_id: task.id },
          order: { index_num: 'ASC' },
        });
        await this.taskRepository.update(task.id, {
          status: ParseTaskStatus.Done,
          progress: 100,
          total_count: Number(result.questions_count || savedCount || 0),
          done_count: Number(result.questions_count || savedCount || 0),
          error: null,
          result_summary: JSON.stringify(
            this.mergeTaskResultSummary(task.result_summary, {
              runtime: runtimeSnapshot,
              debug_dir: debugDir,
              stats: result.stats || {},
              detection: result.detection || result.stats?.detection || null,
              delivery: 'callback_batches',
              debug_file: this.taskAiPreauditDebugFiles.get(task.id) || null,
              dedupe: this.taskQuestionDedupeStats.get(task.id) || null,
            }),
          ),
        });
        await this.writeAiPreauditDebugArtifacts(task, {
          source: 'callback_batches',
          pageCount: Number(result?.stats?.pages_count || 0),
          stats: result.stats || {},
          detection: result.detection || result.stats?.detection || null,
          warnings: result.warnings || result.stats?.warnings || [],
          totalCount: Number(result.questions_count || savedCount || 0),
          finalQuestions,
        });
        await this.refreshBankTotal(task.bank_id);
        this.logger.log(
          `Done parse task id=${task.id} via callback questions=${result.questions_count || 0}`,
        );
      }
    } catch (error) {
      const current = await this.taskRepository.findOne({
        where: { id: task.id },
      });
      if (current?.status === ParseTaskStatus.Paused) {
        this.logger.warn(`Paused parse task id=${task.id}`);
        return;
      }
      if (current?.status === ParseTaskStatus.Canceled) {
        this.logger.warn(`Canceled parse task id=${task.id}`);
        return;
      }
      if (current?.status === ParseTaskStatus.Done) {
        this.logger.warn(`Parse task id=${task.id} finished via late callback after direct PDF call error; preserving done state`);
        await this.taskRepository.update(task.id, { error: null });
        return;
      }
      const message = this.resolveErrorMessage(error);
      this.logger.error(
        `Failed parse task id=${task.id} message=${message}`,
        error instanceof Error ? error.stack : undefined,
      );
      await this.taskRepository.update(task.id, {
        status: ParseTaskStatus.Failed,
        progress: 100,
        error: message,
        result_summary: JSON.stringify(
          this.mergeTaskResultSummary(current?.result_summary, {
            error: message,
          }),
        ),
      });
    } finally {
      this.activeAbortControllers.delete(task.id);
    }
  }

  async appendCallbackMaterials(
    taskId: string,
    materials: Array<Record<string, any>>,
  ) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    if ([ParseTaskStatus.Paused, ParseTaskStatus.Canceled].includes(task.status))
      return { ignored: true, reason: `task ${task.status}` };

    const saved = await this.saveMaterials(task.bank_id, materials, task.id);
    const existing =
      this.callbackMaterialMaps.get(taskId) || new Map<string, Material>();
    for (const [tempId, material] of saved.entries()) {
      existing.set(tempId, material);
    }
    this.callbackMaterialMaps.set(taskId, existing);
    return { saved_count: saved.size };
  }

  async appendCallbackQuestions(
    taskId: string,
    questions: Array<Record<string, any>>,
    total?: number,
  ) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    if ([ParseTaskStatus.Paused, ParseTaskStatus.Canceled].includes(task.status))
      return { ignored: true, reason: `task ${task.status}` };

    const materials =
      this.callbackMaterialMaps.get(taskId) || new Map<string, Material>();
    const saved = await this.saveQuestions(
      task.id,
      task.bank_id,
      questions,
      materials,
    );
    const doneCount = task.done_count + saved.length;
    await this.taskRepository.update(task.id, {
      status: ParseTaskStatus.Processing,
      progress: total
        ? Math.min(95, Math.max(15, Math.round((doneCount / total) * 90)))
        : task.progress,
      total_count: total || task.total_count,
      done_count: doneCount,
      error: null,
    });
    return {
      saved_count: saved.length,
      done_count: doneCount,
      total_count: total || task.total_count,
      dedupe: this.taskQuestionDedupeStats.get(task.id) || null,
    };
  }

  async finishCallbackTask(taskId: string, body: Record<string, any>) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');
    if ([ParseTaskStatus.Paused, ParseTaskStatus.Canceled].includes(task.status))
      return { ignored: true, reason: `task ${task.status}` };

    const doneCount = Number(
      body.done_count || task.done_count || body.total_count || 0,
    );
    const totalCount = Number(body.total_count || doneCount);
    if (this.isZeroQuestionParse(body, [], totalCount)) {
      await this.markTaskZeroQuestionFailure(task.id, {
        stats: body.stats || {},
        detection: body.detection || body.stats?.detection || null,
        delivery: 'callback_batches',
        warnings: body.warnings || body.stats?.warnings || [],
        error: body.error || '未解析到题目',
      });
      await this.writeAiPreauditDebugArtifacts(task, {
        source: 'callback_failed',
        pageCount: Number(body?.pages_count || body?.stats?.pages_count || 0),
        stats: body.stats || {},
        detection: body.detection || body.stats?.detection || null,
        warnings: body.warnings || body.stats?.warnings || [],
        error: body.error || '未解析到题目',
        totalCount,
      });
      this.callbackMaterialMaps.delete(taskId);
      await this.refreshBankTotal(task.bank_id);
      return { status: ParseTaskStatus.Failed, total_count: totalCount };
    }
    const finalQuestions = await this.questionRepository.find({
      where: { parse_task_id: task.id },
      order: { index_num: 'ASC' },
    });
    await this.taskRepository.update(task.id, {
      status: ParseTaskStatus.Done,
      progress: 100,
      total_count: totalCount,
      done_count: doneCount,
      error: null,
      result_summary: JSON.stringify(
        this.mergeTaskResultSummary(task.result_summary, {
          stats: body.stats || {},
          detection: body.detection || body.stats?.detection || null,
          delivery: 'callback_batches',
          debug_file: this.taskAiPreauditDebugFiles.get(task.id) || null,
          dedupe: this.taskQuestionDedupeStats.get(task.id) || null,
        }),
      ),
    });
    await this.writeAiPreauditDebugArtifacts(task, {
      source: 'callback_finish',
      pageCount: Number(body?.pages_count || body?.stats?.pages_count || 0),
      stats: body.stats || {},
      detection: body.detection || body.stats?.detection || null,
      warnings: body.warnings || body.stats?.warnings || [],
      totalCount,
      doneCount,
      finalQuestions,
    });
    this.callbackMaterialMaps.delete(taskId);
    await this.refreshBankTotal(task.bank_id);
    return { status: ParseTaskStatus.Done, total_count: totalCount };
  }

  private isZeroQuestionParse(
    payload: Record<string, any>,
    questions: Array<Record<string, any>> = [],
    totalCount?: number,
  ) {
    const stats = payload?.stats || {};
    const count = Number(
      totalCount ?? payload?.questions_count ?? stats?.total_questions ?? questions.length,
    );
    return (
      count === 0 ||
      payload?.status === 'failed' ||
      stats?.suspected_bad_parse === true ||
      (Array.isArray(payload?.warnings) && payload.warnings.includes('zero_questions_extracted')) ||
      (Array.isArray(stats?.warnings) && stats.warnings.includes('zero_questions_extracted'))
    );
  }

  private async markTaskZeroQuestionFailure(
    taskId: string,
    summary: Record<string, any>,
  ) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    await this.taskRepository.update(taskId, {
      status: ParseTaskStatus.Failed,
      progress: 100,
      total_count: 0,
      done_count: 0,
      error: '未解析到题目',
      result_summary: JSON.stringify(
        this.mergeTaskResultSummary(task?.result_summary, {
          ...summary,
          error: summary.error || '未解析到题目',
          warning: 'zero_questions_extracted',
        }),
      ),
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
    return error instanceof Error ? error.message : 'PDF 解析失败';
  }

  private async getAiConfig(taskId?: string) {
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
        { key: 'MIMO_API_KEY' },
        { key: 'MIMO_BASE_URL' },
        { key: 'MIMO_MODEL' },
        { key: 'MIMO_VISION_MODEL' },
        { key: 'ARK_API_KEY' },
        { key: 'VOLCENGINE_ARK_API_KEY' },
        { key: 'VOLC_ARK_API_KEY' },
        { key: 'ARK_BASE_URL' },
        { key: 'VOLCENGINE_ARK_BASE_URL' },
        { key: 'ARK_CHAT_COMPLETIONS_URL' },
        { key: 'VOLCENGINE_ARK_CHAT_COMPLETIONS_URL' },
        { key: 'ARK_VISION_MODEL' },
        { key: 'VOLCENGINE_ARK_VISION_MODEL' },
        { key: 'ARK_MODEL' },
        { key: 'VOLCENGINE_ARK_MODEL' },
        { key: 'ARK_ENDPOINT_ID' },
        { key: 'VOLCENGINE_ARK_ENDPOINT_ID' },
        { key: 'ARK_API_MODE' },
        { key: 'VOLCENGINE_ARK_API_MODE' },
        { key: 'ARK_RESPONSES_PATH' },
        { key: 'VOLCENGINE_ARK_RESPONSES_PATH' },
        { key: 'VISION_AI_PROVIDER_ORDER' },
        { key: 'VISION_AI_TIMEOUT_SECONDS' },
        { key: 'VISION_AI_PROVIDER_TIMEOUT_SECONDS' },
        { key: 'PDF_VISUAL_PAGE_TIMEOUT_SECONDS' },
        { key: 'PDF_VISUAL_PROVIDER_TIMEOUT_SECONDS' },
        { key: 'PDF_HEADER_FOOTER_BLACKLIST' },
      ],
    });
    const values = new Map(configs.map((config) => [config.key, config.value]));
    const read = (key: string, fallback?: string) =>
      values.get(key) || this.configService.get<string>(key) || fallback || '';
    const compact = (input: Record<string, string>) =>
      Object.fromEntries(
        Object.entries(input).filter(([, value]) => Boolean(value)),
      );

    return compact({
      dashscope_api_key: read('DASHSCOPE_API_KEY'),
      dashscope_base_url: read(
        'DASHSCOPE_BASE_URL',
        'https://dashscope.aliyuncs.com/compatible-mode/v1',
      ),
      visual_model: read('AI_VISUAL_MODEL', 'qwen3-vl-plus'),
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
      mimo_api_key: read('MIMO_API_KEY'),
      mimo_base_url: read('MIMO_BASE_URL', 'https://token-plan-cn.xiaomimimo.com/v1'),
      mimo_model: read('MIMO_MODEL', 'mimo-v2.5'),
      mimo_vision_model: read('MIMO_VISION_MODEL', 'mimo-v2.5'),
      ark_api_key:
        read('ARK_API_KEY') ||
        read('VOLCENGINE_ARK_API_KEY') ||
        read('VOLC_ARK_API_KEY'),
      ark_base_url:
        read('ARK_BASE_URL') ||
        read('VOLCENGINE_ARK_BASE_URL') ||
        read('ARK_CHAT_COMPLETIONS_URL') ||
        read('VOLCENGINE_ARK_CHAT_COMPLETIONS_URL') ||
        'https://ark.cn-beijing.volces.com/api/v3',
      ark_endpoint_id:
        read('ARK_ENDPOINT_ID') || read('VOLCENGINE_ARK_ENDPOINT_ID'),
      ark_vision_model:
        read('ARK_VISION_MODEL') ||
        read('VOLCENGINE_ARK_VISION_MODEL') ||
        read('ARK_MODEL') ||
        read('VOLCENGINE_ARK_MODEL'),
      ark_api_mode:
        read('ARK_API_MODE') ||
        read('VOLCENGINE_ARK_API_MODE') ||
        'responses',
      ark_responses_path:
        read('ARK_RESPONSES_PATH') ||
        read('VOLCENGINE_ARK_RESPONSES_PATH') ||
        '/responses',
      vision_ai_provider_order: read(
        'VISION_AI_PROVIDER_ORDER',
        'volcengine_ark_vl,qwen_vl,mimo_vl',
      ),
      vision_ai_timeout_seconds: read('VISION_AI_TIMEOUT_SECONDS'),
      vision_ai_provider_timeout_seconds: read('VISION_AI_PROVIDER_TIMEOUT_SECONDS'),
      pdf_visual_page_timeout_seconds: read('PDF_VISUAL_PAGE_TIMEOUT_SECONDS'),
      pdf_visual_provider_timeout_seconds: read('PDF_VISUAL_PROVIDER_TIMEOUT_SECONDS'),
      header_footer_blacklist: read('PDF_HEADER_FOOTER_BLACKLIST'),
      parse_task_id: taskId || '',
    });
  }

  private parseJsonArray(value?: string | null) {
    if (!value) return [];
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed)
        ? parsed.map((item) => String(item)).filter(Boolean)
        : [];
    } catch {
      return [];
    }
  }

  private async clearPreviousTaskResults(taskId: string) {
    await this.questionRepository.delete({ parse_task_id: taskId });
    await this.materialRepository.delete({ parse_task_id: taskId });
    this.taskQuestionDedupeStats.delete(taskId);
    this.taskAiPreauditDebugFiles.delete(taskId);
    await rm(this.kernelRunDebugDir(taskId), { recursive: true, force: true }).catch(
      () => undefined,
    );
  }

  private async saveMaterials(
    bankId: string,
    materials: Array<Record<string, any>>,
    taskId?: string,
  ) {
    const saved = new Map<string, Material>();
    for (const raw of materials) {
      const material = await this.materialRepository.save(
        this.materialRepository.create({
          bank_id: bankId,
          parse_task_id: taskId,
          content: this.cleanParsedText(raw.content),
          images: await this.normalizeParsedImages(raw.images || [], taskId, 'material'),
          page_range: this.toNumberArray(raw.page_range ?? raw.pageRange),
          image_refs: this.toStringArray(raw.image_refs ?? raw.imageRefs),
          raw_text: raw.raw_text || raw.rawText || null,
          parse_warnings: this.toStringArray(
            raw.parse_warnings ?? raw.parseWarnings,
          ),
        }),
      );
      if (raw.id) {
        saved.set(raw.id, material);
      }
    }
    return saved;
  }

  private async saveQuestions(
    taskId: string,
    bankId: string,
    questions: Array<Record<string, any>>,
    materials: Map<string, Material>,
  ) {
    const existingQuestions = await this.questionRepository.find({
      where: { parse_task_id: taskId },
    });
    const signatureIndex = new Map<
      string,
      { question: Question; score: number; indexNum: number }
    >();
    for (const question of existingQuestions) {
      const signature = this.buildQuestionSignature(
        {
          content: question.content,
          index: question.index_num,
          option_a: question.option_a,
          option_b: question.option_b,
          option_c: question.option_c,
          option_d: question.option_d,
          page_num: question.page_num,
          page_range: question.page_range,
          images: question.images,
        },
      );
      const score = this.scoreQuestionCompleteness(question);
      if (signature) {
        signatureIndex.set(signature, {
          question,
          score,
          indexNum: question.index_num,
        });
      }
    }

    const existingByIndex = new Map<number, Question>();
    for (const question of existingQuestions) {
      existingByIndex.set(question.index_num, question);
    }

    let stats = this.taskQuestionDedupeStats.get(taskId);
    if (!stats) {
      stats = {
        duplicated_questions_detected: 0,
        duplicated_questions_removed: 0,
        duplicate_signature_hits: [],
      };
      this.taskQuestionDedupeStats.set(taskId, stats);
    }

    const saved: Question[] = [];
    for (const raw of questions) {
      const material = raw.material_id ? materials.get(raw.material_id) : null;
      const images = await this.normalizeParsedImages(raw.images || [], taskId, 'question');
      const options = raw.options || {};
      const source = { ...raw };
      const sourceImages = images;
      const sourceOptions = {
        A: options.A || options.a || raw.option_a,
        B: options.B || options.b || raw.option_b,
        C: options.C || options.c || raw.option_c,
        D: options.D || options.d || raw.option_d,
      };
      const indexNum = this.toNumber(source.index ?? source.index_num, 0);
      const entity = this.questionRepository.create({
        bank_id: bankId,
        parse_task_id: taskId,
        material_id: material?.id,
        index_num: indexNum,
        type:
          source.type === QuestionType.Judge
            ? QuestionType.Judge
            : QuestionType.Single,
        content: this.cleanParsedText(source.content),
        option_a: this.cleanParsedText(sourceOptions.A) || null,
        option_b: this.cleanParsedText(sourceOptions.B) || null,
        option_c: this.cleanParsedText(sourceOptions.C) || null,
        option_d: this.cleanParsedText(sourceOptions.D) || null,
        answer: source.answer || null,
        analysis: this.cleanParsedText(source.analysis) || null,
        images: sourceImages,
        ai_image_desc: sourceImages
          .map((image) => image.ai_desc)
          .filter(Boolean)
          .join('\n'),
        page_num: this.toOptionalNumber(
          source.page_num ?? source.page ?? source.pageNumber,
        ),
        page_range: this.toNumberArray(source.page_range ?? source.pageRange),
        source_page_start: this.toOptionalNumber(
          source.source_page_start ?? source.sourcePageStart,
        ),
        source_page_end: this.toOptionalNumber(
          source.source_page_end ?? source.sourcePageEnd,
        ),
        source_bbox: this.toNumberArray(source.source_bbox ?? source.sourceBbox),
        source_text_span:
          this.cleanParsedText(source.source_text_span ?? source.sourceTextSpan) || null,
        source_anchor_text: source.source_anchor_text || source.sourceAnchorText || null,
        source_confidence: this.toOptionalNumber(
          source.source_confidence ?? source.sourceConfidence,
        ),
        material_group_id: source.material_group_id || source.materialGroupId || null,
        material_group_question_indexes: this.toNumberArray(
          source.material_group_question_indexes ?? source.materialGroupQuestionIndexes,
        ),
        material_group_confidence: this.toOptionalNumber(
          source.material_group_confidence ?? source.materialGroupConfidence,
        ),
        material_group_reason:
          source.material_group_reason || source.materialGroupReason || null,
        shared_material: Boolean(source.shared_material ?? source.sharedMaterial),
        image_refs: this.toStringArray(source.image_refs ?? source.imageRefs),
        visual_refs: Array.isArray(source.visual_refs ?? source.visualRefs)
          ? source.visual_refs ?? source.visualRefs
          : null,
        source: source.source || source.parse_source || null,
        raw_text: source.raw_text || source.rawText || null,
        parse_confidence: this.toOptionalNumber(
          source.parse_confidence ?? source.confidence,
        ),
        parse_warnings: this.toStringArray(
          source.parse_warnings ?? source.parseWarnings,
        ),
        ai_corrections: Array.isArray(source.ai_corrections ?? source.aiCorrections)
          ? source.ai_corrections ?? source.aiCorrections
          : null,
        ai_confidence: this.toOptionalNumber(
          source.ai_confidence ?? source.aiConfidence,
        ),
        ai_provider: source.ai_provider || source.aiProvider || null,
        ai_review_notes: source.ai_review_notes || source.aiReviewNotes || null,
        ai_candidate_answer:
          source.ai_candidate_answer || source.aiCandidateAnswer || null,
        ai_candidate_analysis:
          source.ai_candidate_analysis || source.aiCandidateAnalysis || null,
        ai_answer_confidence: this.toOptionalNumber(
          source.ai_answer_confidence ?? source.aiAnswerConfidence,
        ),
        ai_reasoning_summary:
          source.ai_reasoning_summary || source.aiReasoningSummary || null,
        ai_knowledge_points: this.toStringArray(
          source.ai_knowledge_points ?? source.aiKnowledgePoints,
        ),
        ai_risk_flags: this.toStringArray(
          source.ai_risk_flags ?? source.aiRiskFlags,
        ),
        ai_solver_provider:
          source.ai_solver_provider || source.aiSolverProvider || null,
        ai_solver_model: source.ai_solver_model || source.aiSolverModel || null,
        ai_solver_first_model:
          source.ai_solver_first_model || source.aiSolverFirstModel || null,
        ai_solver_final_model:
          source.ai_solver_final_model || source.aiSolverFinalModel || null,
        ai_solver_rechecked: Boolean(
          source.ai_solver_rechecked ?? source.aiSolverRechecked,
        ),
        ai_solver_recheck_reason:
          source.ai_solver_recheck_reason || source.aiSolverRecheckReason || null,
        ai_solver_recheck_result:
          source.ai_solver_recheck_result || source.aiSolverRecheckResult || null,
        ai_solver_created_at:
          source.ai_solver_created_at || source.aiSolverCreatedAt || null,
        ai_answer_conflict: Boolean(
          source.ai_answer_conflict ?? source.aiAnswerConflict,
        ),
        visual_summary: source.visual_summary || source.visualSummary || null,
        visual_confidence: this.toOptionalNumber(
          source.visual_confidence ?? source.visualConfidence,
        ),
        visual_parse_status:
          source.visual_parse_status || source.visualParseStatus || null,
        visual_error: source.visual_error || source.visualError || null,
        visual_risk_flags: this.toStringArray(
          source.visual_risk_flags ?? source.visualRiskFlags,
        ),
        has_visual_context: Boolean(
          source.has_visual_context ?? source.hasVisualContext,
        ),
        answer_unknown_reason:
          source.answer_unknown_reason || source.answerUnknownReason || null,
        analysis_unknown_reason:
          source.analysis_unknown_reason || source.analysisUnknownReason || null,
        ai_audit_status: source.ai_audit_status || source.aiAuditStatus || null,
        ai_audit_verdict: source.ai_audit_verdict || source.aiAuditVerdict || null,
        ai_audit_summary:
          source.ai_audit_summary || source.aiAuditSummary || null,
        ai_can_understand_question: Boolean(
          source.ai_can_understand_question ?? source.aiCanUnderstandQuestion,
        ),
        ai_can_solve_question: Boolean(
          source.ai_can_solve_question ?? source.aiCanSolveQuestion,
        ),
        ai_reviewed_before_human: Boolean(
          source.ai_reviewed_before_human ?? source.aiReviewedBeforeHuman,
        ),
        ai_review_error: source.ai_review_error || source.aiReviewError || null,
        question_quality:
          source.question_quality || source.questionQuality || null,
        status: QuestionStatus.Draft,
        needs_review: Boolean(source.needs_review || source.parse_warnings?.length),
        review_status: Boolean(source.needs_review || source.parse_warnings?.length)
          ? QuestionReviewStatus.NeedsReview
          : QuestionReviewStatus.Pending,
      });
      const signature = this.buildQuestionSignature({
        content: entity.content,
        index: indexNum,
        option_a: entity.option_a,
        option_b: entity.option_b,
        option_c: entity.option_c,
        option_d: entity.option_d,
        page_num: entity.page_num,
        page_range: entity.page_range,
        images: sourceImages,
        source_page_start: entity.source_page_start,
        source_page_end: entity.source_page_end,
      });

      const candidateScore = this.scoreQuestionCompleteness(entity);
      const bySignature = signature ? signatureIndex.get(signature) : undefined;
      if (bySignature) {
        stats.duplicated_questions_detected += 1;
        stats.duplicate_signature_hits.push(signature);

        if (candidateScore > bySignature.score) {
          Object.assign(bySignature.question, entity, { id: bySignature.question.id });
          const persisted = await this.questionRepository.save(
            bySignature.question,
          );
          saved.push(await this.ensureImageQuestionLinks(persisted));
          existingByIndex.set(indexNum, bySignature.question);
        } else {
          stats.duplicated_questions_removed += 1;
        }
        continue;
      }

      const byIndex = existingByIndex.get(indexNum);
      if (byIndex && this.shouldReplaceQuestion(byIndex, entity, candidateScore)) {
        stats.duplicated_questions_detected += 1;
        Object.assign(byIndex, entity, { id: byIndex.id });
        const persisted = await this.questionRepository.save(byIndex);
        existingByIndex.set(indexNum, byIndex);
        saved.push(await this.ensureImageQuestionLinks(persisted));
        continue;
      }
      if (byIndex) {
        stats.duplicated_questions_detected += 1;
        stats.duplicated_questions_removed += 1;
        continue;
      }

      const persisted = await this.questionRepository.save(entity);
      existingByIndex.set(indexNum, persisted);
      if (signature) {
        signatureIndex.set(signature, {
          question: persisted,
          score: candidateScore,
          indexNum,
        });
      }
      saved.push(await this.ensureImageQuestionLinks(persisted));
    }
    return saved;
  }

  private async refreshBankTotal(bankId: string) {
    const total = await this.questionRepository.count({
      where: { bank_id: bankId },
    });
    await this.bankRepository.update(bankId, { total_count: total });
  }

  private isPublishableParsedQuestion(question: Question) {
    const warnings = Array.isArray(question.parse_warnings)
      ? question.parse_warnings
      : [];
    const aiStatus = String(question.ai_audit_status || '').trim();
    const hasAiPreauditSignal = Boolean(
      aiStatus || question.ai_reviewed_before_human || question.ai_review_error,
    );
    return (
      !question.needs_review &&
      warnings.length === 0 &&
      (!hasAiPreauditSignal ||
        (aiStatus === 'passed' && !question.ai_review_error))
    );
  }

  private buildQuestionSignature(input: {
    content?: unknown;
    index?: number;
    option_a?: unknown;
    option_b?: unknown;
    option_c?: unknown;
    option_d?: unknown;
    page_num?: unknown;
    page_range?: unknown;
    source_page_start?: unknown;
    source_page_end?: unknown;
    images?: unknown;
  }) {
    const content = this.normalizeTextForSignature(input.content);
    const options = [
      this.normalizeTextForSignature(input.option_a),
      this.normalizeTextForSignature(input.option_b),
      this.normalizeTextForSignature(input.option_c),
      this.normalizeTextForSignature(input.option_d),
    ];
    if (!content && !options.some(Boolean)) {
      return null;
    }

    const imageCount = Array.isArray(input.images)
      ? input.images.length
      : 0;
    const pages = Array.from(
      new Set([
        this.toOptionalNumber(input.page_num),
        this.toOptionalNumber(input.source_page_start),
        this.toOptionalNumber(input.source_page_end),
        ...(Array.isArray(input.page_range)
          ? input.page_range
              .map((value) => this.toOptionalNumber(value))
              .filter((value) => value !== null)
          : []),
      ]),
    )
      .filter((value) => value !== null)
      .map((value) => value as number);
    if (!pages.length) {
      pages.push(this.toNumber(input.index || 0, 0));
    }

    const payload = {
      stem: content,
      options,
      pages: pages.sort((a, b) => a - b),
      image_count: imageCount,
    };
    return JSON.stringify(payload);
  }

  private normalizeTextForSignature(value: unknown) {
    return String(value || '')
      .replace(/[\s\u00a0\t\r\n]+/g, '')
      .replace(/\p{P}/gu, '')
      .slice(0, 500)
      .toLowerCase();
  }

  private scoreQuestionCompleteness(question: any) {
    let score = 0;
    if (String(question.content || '').trim()) score += 4;
    for (const label of ['a', 'b', 'c', 'd'] as const) {
      const value = question[`option_${label}`];
      if (String(value || '').trim()) score += 2;
    }
    if (question.ai_audit_status === 'passed') score += 5;
    if (question.ai_audit_status === 'warning') score += 2;
    if (question.ai_audit_status === 'failed') score += 0;
    if (question.ai_can_solve_question) score += 3;
    if (question.visual_parse_status === 'success') score += 2;
    if (question.visual_parse_status === 'partial') score += 1;
    if (question.visual_parse_status === 'failed') score -= 1;
    if (question.ai_reviewed_before_human) score += 2;
    const warnings = this.toStringArray(question.parse_warnings);
    score -= warnings.length;
    return score;
  }

  private shouldReplaceQuestion(
    existing: Question,
    incoming: Question,
    incomingScore: number,
  ) {
    const replaceThreshold = this.scoreQuestionCompleteness(existing) + 1;
    return incomingScore > replaceThreshold;
  }

  private async writeAiPreauditDebugArtifacts(
    task: ParseTask,
    payload: {
      source: string;
      pageCount: number;
      stats?: Record<string, any>;
      detection?: Record<string, any> | null;
      warnings?: Array<string | unknown>;
      error?: string;
      savedCount?: number;
      totalCount?: number;
      doneCount?: number;
      finalQuestions?: Question[];
      extractedQuestionsBeforeAudit?: Array<Record<string, unknown>>;
      extractedQuestions?: Array<Record<string, unknown>>;
    },
  ) {
    const debugDir = join(
      process.cwd(),
      'debug',
      'pdf-ai-preaudit',
      task.id,
    );
    await mkdir(debugDir, { recursive: true });
    const kernelDebugDir =
      payload.stats?.scanned_fallback_debug?.kernel_debug_dir ||
      null;

    const readJson = async (path: string | null) => {
      if (!path) return null;
      try {
        const content = await readFile(path, 'utf-8');
        return JSON.parse(content);
      } catch {
        return null;
      }
    };

    const writeArtifact = async (name: string, value: unknown) => {
      await writeFile(
        join(debugDir, name),
        JSON.stringify(value, null, 2),
        'utf-8',
      );
    };

    const ensurePath = (value: unknown) =>
      typeof value === 'string' && value ? value : null;

    const readKernelVisionRawOutputs = async () => {
      if (!kernelDebugDir) return [];
      const visionDir = join(kernelDebugDir, 'debug', 'vision_ai_inputs');
      try {
        const names = await readdir(visionDir);
        const rawFiles = names
          .filter((name) => /^page_\d+_raw_output\.json$/.test(name))
          .sort((a, b) => {
            const pageA = Number(a.match(/^page_(\d+)_/)?.[1] || 0);
            const pageB = Number(b.match(/^page_(\d+)_/)?.[1] || 0);
            return pageA - pageB;
          });
        const outputs = await Promise.all(
          rawFiles.map((name) => readJson(join(visionDir, name))),
        );
        return outputs.filter((item) => item && typeof item === 'object') as Array<Record<string, any>>;
      } catch {
        return [];
      }
    };

    const readKernelPrompt = async () => {
      if (!kernelDebugDir) return null;
      try {
        return await readFile(
          join(kernelDebugDir, 'debug', 'vision_ai_inputs', 'page_parse_prompt.txt'),
          'utf-8',
        );
      } catch {
        return null;
      }
    };

    const kernelRawOutputs = await readKernelVisionRawOutputs();
    const kernelPrompt = await readKernelPrompt();
    const kernelVisionStats = kernelRawOutputs.length
      ? {
          enabled: true,
          called_pages: kernelRawOutputs
            .map((item) => Number(item.page))
            .filter((page) => Number.isFinite(page)),
          calledPages: kernelRawOutputs
            .map((item) => Number(item.page))
            .filter((page) => Number.isFinite(page)),
          qwen_vl_raw_outputs: kernelRawOutputs,
          qwen_vl_prompt: kernelPrompt,
        }
      : null;

    const qwenStats =
      (payload.stats &&
        ((payload.stats as any).vision_ai || (payload.stats as any).visionAi || (payload.stats as any).vision_ai_stats)) ||
      (payload.stats as any).scanned_fallback_debug?.vision_ai ||
      kernelVisionStats ||
      null;
    const calledPages: Array<unknown> = Array.isArray(qwenStats?.called_pages)
      ? qwenStats.called_pages
      : Array.isArray(qwenStats?.calledPages)
        ? qwenStats.calledPages
        : [];

    const finalQuestions = payload.finalQuestions || [];
    const qwenRawOutputs = Array.isArray(
      qwenStats?.qwen_vl_raw_outputs,
    )
      ? qwenStats.qwen_vl_raw_outputs
      : [];
    const qwenInputs = calledPages.map((page) => {
      const record = qwenRawOutputs.find(
        (item) => item?.page === page,
      );
      const requestPayload =
        record && typeof record.request_payload === 'object'
          ? (record.request_payload as Record<string, any>)
          : {};
      return {
        page,
        original_page_image: ensurePath(
          requestPayload.page_image_path ||
            requestPayload.page_image ||
            requestPayload.original_page_image,
        ),
        crop_image: ensurePath(requestPayload.crop_image_path),
        prompt_path: ensurePath(requestPayload.prompt_path),
        prompt_preview: requestPayload.prompt ? String(requestPayload.prompt).slice(0, 1000) : null,
      };
    });
    const qwenPrompt =
      (qwenStats?.qwen_vl_prompt || qwenStats?.prompt || null) ||
      qwenRawOutputs.find((item) => item && item.prompt)?.prompt ||
      null;
    const qwenPromptPath = qwenRawOutputs.find((item) => item?.request_payload)?.request_payload
      ?.prompt_path as string | undefined || null;
    const pageUnderstanding = await readJson(
      kernelDebugDir ? join(kernelDebugDir, 'debug', 'page-understanding.json') : null,
    );
    const semanticGroups = await readJson(
      kernelDebugDir ? join(kernelDebugDir, 'debug', 'semantic-groups.json') : null,
    );
    const recropPlan = await readJson(
      kernelDebugDir ? join(kernelDebugDir, 'debug', 'recrop-plan.json') : null,
    );
    const kernelStageCounts = await readJson(
      kernelDebugDir ? join(kernelDebugDir, 'debug', 'stage-counts.json') : null,
    );
    const kernelFirstFailedStage = await readJson(
      kernelDebugDir ? join(kernelDebugDir, 'debug', 'first-failed-stage.json') : null,
    );
    const fallbackRecovery = await readJson(
      kernelDebugDir ? join(kernelDebugDir, 'debug', 'fallback-recovery.json') : null,
    );
    const questionNumberScan = await readJson(
      kernelDebugDir ? join(kernelDebugDir, 'debug', 'question-number-scan.json') : null,
    );
    const pageUnderstandingRecovered = await readJson(
      kernelDebugDir
        ? join(kernelDebugDir, 'debug', 'page-understanding-recovered.json')
        : null,
    );
    const sourceTextSpanReport = await readJson(
      kernelDebugDir ? join(kernelDebugDir, 'debug', 'source-text-span-report.json') : null,
    );
    const materialGroupBindingReport = await readJson(
      kernelDebugDir
        ? join(kernelDebugDir, 'debug', 'material-group-binding-report.json')
        : null,
    );
    const visualMergeCandidates = await readJson(
      kernelDebugDir
        ? join(kernelDebugDir, 'debug', 'visual_merge_candidates.json')
        : null,
    );
    const pageUnderstandingList = Array.isArray(pageUnderstanding)
      ? pageUnderstanding as Array<Record<string, any>>
      : [];
    const semanticGroupList = Array.isArray(semanticGroups)
      ? semanticGroups as Array<Record<string, any>>
      : [];
    const recropPlanList = Array.isArray(recropPlan)
      ? recropPlan as Array<Record<string, any>>
      : [];
    const previewFallbacks = finalQuestions.length
      ? []
      : semanticGroupList.map((group, index) => {
          const sourceStart = Number(group.source_page_start || 0) || null;
          const sourceEnd = Number(group.source_page_end || sourceStart || 0) || sourceStart;
          const sourcePages = sourceStart && sourceEnd
            ? Array.from(
                { length: Math.max(1, sourceEnd - sourceStart + 1) },
                (_, offset) => sourceStart + offset,
              )
            : [];
          const pageRecord = pageUnderstandingList.find((item) =>
            Number(item.page_no || item.page_num) === sourceStart,
          );
          const matchingRecrop =
            recropPlanList.find((item) => item.question_no === group.question_no) ||
            recropPlanList[index] ||
            null;
          const riskFlags = this.toStringArray(group.risk_flags || matchingRecrop?.risk_flags || []);
          const options = this.optionsFromSemanticGroup(group);
          return {
            question_no: group.question_no ?? null,
            stem: group.stem_group?.text || null,
            options,
            visual_assets: group.visual_group?.blocks || [],
            preview_image_path: pageRecord?.source_image_path || null,
            source_page_refs: sourcePages,
            visual_parse_status: 'failed',
            visual_summary: group.grouping_reason || pageRecord?.reason || 'parser_fallback_uncertain_page_group',
            risk_flags: Array.from(new Set([...riskFlags, 'need_manual_fix'])),
            need_manual_fix: true,
            source_artifacts_refs: {
              page_understanding: kernelDebugDir ? join(kernelDebugDir, 'debug', 'page-understanding.json') : null,
              semantic_groups: kernelDebugDir ? join(kernelDebugDir, 'debug', 'semantic-groups.json') : null,
              recrop_plan: kernelDebugDir ? join(kernelDebugDir, 'debug', 'recrop-plan.json') : null,
              raw_output_ref: pageRecord?.raw_output_ref || null,
            },
          };
        });
    const finalQuestionsPayload = finalQuestions.map((question) =>
      this.serializeQuestionForDebug(question),
    );
    const finalQuestionPreviews: Array<Record<string, any>> = finalQuestions.map((question) => {
      const firstImage = Array.isArray(question.images) ? (question.images[0] as any) : null;
      return {
        question_no: question.index_num,
        stem: question.content,
        options: {
          A: question.option_a,
          B: question.option_b,
          C: question.option_c,
          D: question.option_d,
        },
        visual_assets: question.images || [],
        images: question.images || [],
        image_refs: question.image_refs || [],
        preview_image_path: firstImage?.url || null,
        source_page_refs: this.questionSourcePageRefsFromEntity(question),
        source_bbox: question.source_bbox || null,
        source_text_span: question.source_text_span || null,
        source_anchor_text: question.source_anchor_text || null,
        material_group_id: question.material_group_id || null,
        material_group_question_indexes: question.material_group_question_indexes || [],
        material_group_confidence: question.material_group_confidence ?? null,
        material_group_reason: question.material_group_reason || null,
        shared_material: Boolean(question.shared_material),
        visual_summary: question.visual_summary,
        visual_parse_status: question.visual_parse_status,
        ai_audit_status: question.ai_audit_status,
        ai_audit_verdict: question.ai_audit_verdict,
        need_manual_fix: Boolean(question.needs_review || question.ai_audit_status !== 'passed'),
        needs_review: question.needs_review,
        risk_flags: question.ai_risk_flags,
        source_artifacts_refs: {
          page_understanding: kernelDebugDir ? join(kernelDebugDir, 'debug', 'page-understanding.json') : null,
          semantic_groups: kernelDebugDir ? join(kernelDebugDir, 'debug', 'semantic-groups.json') : null,
          recrop_plan: kernelDebugDir ? join(kernelDebugDir, 'debug', 'recrop-plan.json') : null,
        },
      };
    });
    const finalPreviewPayload = {
      taskId: task.id,
      bankId: task.bank_id,
      questions: [...finalQuestionPreviews, ...previewFallbacks],
    };
    const stageCounts = {
      ...(kernelStageCounts && typeof kernelStageCounts === 'object' ? kernelStageCounts : {}),
      final_questions_count: finalQuestionsPayload.length,
      final_preview_questions_count: finalPreviewPayload.questions.length,
    };
    const backendFinalPreviewDropAll =
      Number(stageCounts.output_questions_count || finalQuestionsPayload.length || 0) > 0 &&
      finalPreviewPayload.questions.length === 0;
    const firstFailedStage = backendFinalPreviewDropAll
      ? {
          firstFailedStage: 'backend_final_preview',
          reason: 'kernel/output_questions 非空，但 final_preview_payload.questions 为空',
          stage_counts: stageCounts,
        }
      : kernelFirstFailedStage || {
          firstFailedStage: finalPreviewPayload.questions.length ? null : 'backend_final_preview',
          reason: finalPreviewPayload.questions.length
            ? 'no backend final preview failure detected'
            : 'final_preview_payload.questions is empty',
          stage_counts: stageCounts,
        };
    const aiAuditResults = finalQuestions.length
      ? finalQuestions.map((question) => {
          const optionsComplete = Boolean(question.option_a && question.option_b && question.option_c && question.option_d);
          const riskFlags = this.toStringArray(question.ai_risk_flags || []);
          return {
            question_no: question.index_num,
            ai_audit_status: question.ai_audit_status,
            ai_audit_verdict: question.ai_audit_verdict,
            ai_audit_summary: question.ai_audit_summary,
            can_human_understand: Boolean(question.ai_can_understand_question),
            can_answer: Boolean(question.ai_can_solve_question),
            is_stem_complete: Boolean(question.content && !this.containsForbiddenPlaceholder(question.content)),
            are_options_complete: optionsComplete,
            are_images_complete: question.visual_parse_status === 'success',
            has_chart_title: !riskFlags.includes('chart_title_missing_or_unlocalized'),
            has_table_header: !riskFlags.includes('table_header_missing_or_unlocalized'),
            has_broken_image: riskFlags.some((flag) => flag.includes('broken') || flag.includes('fragment')),
            answer_suggestion: question.ai_candidate_answer || null,
            answer_confidence: question.ai_answer_confidence ?? null,
            answer_unknown_reason: question.answer_unknown_reason || null,
            analysis_suggestion: question.ai_candidate_analysis || null,
            analysis_confidence: (question as any).ai_analysis_confidence ?? null,
            analysis_unknown_reason: question.analysis_unknown_reason || null,
            risk_flags: riskFlags,
            suggested_action: question.ai_audit_status === 'passed' ? 'human_review' : 'manual_fix_before_import',
            ai_can_understand_question: question.ai_can_understand_question,
            ai_can_solve_question: question.ai_can_solve_question,
            needs_review: question.needs_review,
          };
        })
      : semanticGroupList.map((group, index) => {
          const matchingRecrop =
            recropPlanList.find((item) => item.question_no === group.question_no) ||
            recropPlanList[index] ||
            null;
          const riskFlags = Array.from(
            new Set([
              ...this.toStringArray(group.risk_flags || []),
              ...this.toStringArray(matchingRecrop?.risk_flags || []),
              'need_manual_fix',
            ]),
          );
          const options = this.optionsFromSemanticGroup(group);
          const stemComplete = Boolean(this.safeDisplayText(group.stem_group?.text, ''));
          const optionsComplete = ['A', 'B', 'C', 'D'].every((label) =>
            Boolean(this.safeDisplayText(options[label], '')),
          );
          const hasVisual = Array.isArray(group.visual_group?.blocks) && group.visual_group.blocks.length > 0;
          const fallbackAuditStatus = stemComplete && optionsComplete && hasVisual ? 'warning' : 'failed';
          return {
            question_no: group.question_no ?? null,
            ai_audit_status: fallbackAuditStatus,
            ai_audit_verdict: fallbackAuditStatus === 'warning' ? '需复核' : '不建议入库',
            ai_audit_summary: group.grouping_reason || '外部视觉模型未返回可结构化题目，需人工重裁切/复核',
            can_human_understand: stemComplete && optionsComplete,
            can_answer: false,
            is_stem_complete: stemComplete,
            are_options_complete: optionsComplete,
            are_images_complete: hasVisual,
            has_chart_title: false,
            has_table_header: false,
            has_broken_image: !hasVisual,
            answer_suggestion: null,
            answer_confidence: null,
            answer_unknown_reason: 'vision_ai_failed_or_unstructured_output',
            analysis_suggestion: null,
            analysis_confidence: null,
            analysis_unknown_reason: 'vision_ai_failed_or_unstructured_output',
            risk_flags: riskFlags,
            suggested_action: 'manual_fix_before_import',
          };
        });
    const placeholderFiltered = finalQuestions.filter((question) =>
      [question.content, question.analysis, question.option_a, question.option_b, question.option_c, question.option_d]
        .some((value) =>
          this.containsForbiddenPlaceholder(value),
        ),
    ).length;

    const dedupe = this.taskQuestionDedupeStats.get(task.id) || {
      duplicated_questions_detected: 0,
      duplicated_questions_removed: 0,
      duplicate_signature_hits: [],
    };
    const debugPayload: Record<string, any> = {
      taskId: task.id,
      bankId: task.bank_id,
      pdf_path: task.file_url || null,
      pages_processed: this.toNumber(payload.pageCount || 0, 0),
      qwen_vl_enabled: !!qwenStats?.enabled,
      qwen_vl_call_count_before: calledPages.length,
      qwen_vl_call_count_after: calledPages.length,
      qwen_vl_inputs: qwenInputs,
      qwen_vl_prompt: qwenPrompt,
      qwen_vl_raw_outputs: qwenRawOutputs,
      qwen_vl_prompt_path: qwenPromptPath,
      parsed_visual_results: payload.stats?.parsed_visual_results || null,
      extracted_questions_before_audit:
        payload.extractedQuestionsBeforeAudit ||
        payload.extractedQuestions ||
        payload.stats?.raw_questions ||
        [],
      ai_audit_results: aiAuditResults,
      answer_suggestions: finalQuestions.map((question) => ({
        question_no: question.index_num,
        answer_suggestion: question.ai_candidate_answer,
        answer_unknown_reason: question.answer_unknown_reason,
        answer_confidence: question.ai_answer_confidence,
      })),
      analysis_suggestions: finalQuestions.map((question) => ({
        question_no: question.index_num,
        analysis_suggestion: question.ai_candidate_analysis,
        analysis_unknown_reason: question.analysis_unknown_reason,
      })),
      final_questions_after_audit: finalQuestionsPayload,
      final_preview_payload: finalPreviewPayload,
      stage_counts: stageCounts,
      first_failed_stage: firstFailedStage,
      page_understanding: pageUnderstanding || payload.stats?.scanned_fallback_debug?.page_understanding || null,
      semantic_groups: semanticGroups || payload.stats?.scanned_fallback_debug?.semantic_groups || null,
      recrop_plan: recropPlan || payload.stats?.scanned_fallback_debug?.recrop_plan || null,
      fallback_recovery: fallbackRecovery || null,
      question_number_scan: questionNumberScan || null,
      page_understanding_recovered: pageUnderstandingRecovered || null,
      source_text_span_report: sourceTextSpanReport || null,
      material_group_binding_report: materialGroupBindingReport || null,
      visual_merge_candidates:
        visualMergeCandidates ||
        payload.stats?.scanned_fallback_debug?.visual_merge_candidates ||
        null,
      images_linkage: finalQuestions.map((question) => ({
        question_no: question.index_num,
        question_id: question.id,
        links: Array.isArray(question.images)
          ? question.images.map((image: any) => ({
              ref: image?.ref,
              url: image?.url,
              belongs_to_question: image?.belongs_to_question,
              linked_question_id: image?.linked_question_id,
              linked_question_no: image?.linked_question_no,
              linked_by: image?.linked_by,
              link_reason: image?.link_reason,
            }))
          : [],
      })),
      duplicated_questions_detected: dedupe.duplicated_questions_detected,
      duplicated_questions_removed: dedupe.duplicated_questions_removed,
      duplicate_signature_hits: dedupe.duplicate_signature_hits,
      placeholder_filtered_count: placeholderFiltered || payload.stats?.placeholder_filtered_count || 0,
      visual_parse_failures:
        Array.isArray(payload.warnings) &&
        payload.warnings.filter((item) =>
          String(item).includes('visual'),
        ),
      ai_audit_failures: finalQuestions
        .filter((question) => !question.ai_reviewed_before_human)
        .map((question) => ({
          question_no: question.index_num,
          reason: question.ai_review_error || question.ai_audit_summary,
        })),
      risk_flags: finalQuestions.flatMap((question) =>
        this.toStringArray(question.ai_risk_flags),
      ),
      final_verdict: {
        saved_count: payload.finalQuestions?.length || payload.savedCount || 0,
        total_count: payload.totalCount || finalQuestions.length || 0,
        done_count: payload.doneCount || finalQuestions.length,
        error: payload.error || null,
        warnings: this.toStringArray(payload.warnings || []),
      },
    };

    const debugPath = join(debugDir, 'ai-preaudit-debug.json');
    await writeFile(
      debugPath,
      JSON.stringify(debugPayload, null, 2),
      'utf-8',
    );
    await writeArtifact('final-questions.json', finalQuestionsPayload);
    await writeArtifact('final-preview-payload.json', finalPreviewPayload);
    await writeArtifact('ai-audit-results.json', aiAuditResults);
    await writeArtifact('stage-counts.json', stageCounts);
    await writeArtifact('first-failed-stage.json', firstFailedStage);
    if (qwenPromptPath) {
      await writeArtifact('qwen-vl-prompt.txt', qwenPrompt || '');
    } else if (qwenPrompt) {
      await writeFile(
        join(debugDir, 'qwen-vl-prompt.txt'),
        String(qwenPrompt),
        'utf-8',
      );
    }
    if (qwenRawOutputs.length) {
      await writeArtifact('qwen-vl-raw-outputs.json', qwenRawOutputs);
    }
    if (pageUnderstanding) {
      await writeArtifact('page-understanding.json', pageUnderstanding);
    }
    if (semanticGroups) {
      await writeArtifact('semantic-groups.json', semanticGroups);
    }
    if (recropPlan) {
      await writeArtifact('recrop-plan.json', recropPlan);
    }
    if (fallbackRecovery) {
      await writeArtifact('fallback-recovery.json', fallbackRecovery);
    }
    if (questionNumberScan) {
      await writeArtifact('question-number-scan.json', questionNumberScan);
    }
    if (pageUnderstandingRecovered) {
      await writeArtifact(
        'page-understanding-recovered.json',
        pageUnderstandingRecovered,
      );
    }
    if (sourceTextSpanReport) {
      await writeArtifact('source-text-span-report.json', sourceTextSpanReport);
    }
    if (materialGroupBindingReport) {
      await writeArtifact(
        'material-group-binding-report.json',
        materialGroupBindingReport,
      );
    }
    if (visualMergeCandidates) {
      await writeArtifact('visual-merge-candidates.json', visualMergeCandidates);
    }
    this.taskAiPreauditDebugFiles.set(task.id, debugPath);

    if (payload.stats?.scanned_fallback_debug?.kernel_debug_dir) {
      const copiedPath = join(debugDir, 'kernel_debug_dir.txt');
      await writeFile(
        copiedPath,
        JSON.stringify(
          {
            kernel_debug_dir: payload.stats.scanned_fallback_debug.kernel_debug_dir,
          },
          null,
          2,
        ),
        'utf-8',
      );
    }

    return {
      debugFile: debugPath,
      aiPreauditCount: finalQuestions.length,
    };
  }

  private questionSourcePageRefsFromEntity(question: Question) {
    const start = this.toOptionalNumber(question.source_page_start ?? question.page_num);
    const end = this.toOptionalNumber(question.source_page_end) || start;
    if (start && end && end >= start && end - start <= 50) {
      return Array.from({ length: end - start + 1 }, (_unused, index) => start + index);
    }
    const pageRange = this.toNumberArray(question.page_range);
    return pageRange || [];
  }

  private serializeQuestionForDebug(question: Question) {
    return {
      id: question.id,
      question_no: question.index_num,
      stem: question.content,
      options: {
        A: question.option_a,
        B: question.option_b,
        C: question.option_c,
        D: question.option_d,
      },
      images: question.images || [],
      image_refs: question.image_refs || [],
      answer: question.answer,
      analysis: question.analysis,
      visual_parse_status: question.visual_parse_status,
      visual_summary: question.visual_summary,
      visual_confidence: question.visual_confidence,
      visual_error: question.visual_error,
      ai_candidate_answer: question.ai_candidate_answer,
      ai_candidate_analysis: question.ai_candidate_analysis,
      answer_unknown_reason: question.answer_unknown_reason,
      analysis_unknown_reason: question.analysis_unknown_reason,
      ai_audit_status: question.ai_audit_status,
      ai_audit_verdict: question.ai_audit_verdict,
      ai_audit_summary: question.ai_audit_summary,
      ai_can_understand_question: question.ai_can_understand_question,
      ai_can_solve_question: question.ai_can_solve_question,
      ai_reviewed_before_human: question.ai_reviewed_before_human,
      ai_review_error: question.ai_review_error,
      question_quality: question.question_quality,
      needs_review: question.needs_review,
      parse_warnings: question.parse_warnings || [],
      ai_risk_flags: question.ai_risk_flags || [],
      page_num: question.page_num,
      page_range: question.page_range,
      source_page_start: question.source_page_start,
      source_page_end: question.source_page_end,
      source_bbox: question.source_bbox,
      source_text_span: question.source_text_span,
      source_anchor_text: question.source_anchor_text,
      source_confidence: question.source_confidence,
      material_group_id: question.material_group_id,
      material_group_question_indexes: question.material_group_question_indexes || [],
      material_group_confidence: question.material_group_confidence,
      material_group_reason: question.material_group_reason,
      shared_material: Boolean(question.shared_material),
      created_at: question.created_at,
    };
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

  private toStringArray(value: unknown) {
    if (!Array.isArray(value)) return [];
    return value.map((item) => String(item)).filter(Boolean);
  }

  private toArrayOfObjects(value: unknown) {
    if (!Array.isArray(value)) return [];
    return value.filter(
      (item): item is Record<string, any> =>
        Boolean(item) && typeof item === 'object',
    );
  }

  private cleanParsedText(value: unknown) {
    return String(value || '')
      .split(/\r?\n/)
      .map((line) =>
        line
          .replace(/\[?\s*(?:page\s*\d+\s*)?visual\s+parse\s+(?:unavailable|failed|error)[^\]\r\n]*\]?/gi, '')
          .trim(),
      )
      .filter(
        (line) =>
          line &&
          !['【', '】'].includes(line.trim()) &&
          !/^\[?\s*unavailable\s*\]?$/i.test(line),
      )
      .join('\n')
      .trim()
      .replace(/^】+/, '')
      .replace(/【+$/, '')
      .trim();
  }

  private containsForbiddenPlaceholder(value: unknown) {
    if (value === null || value === undefined) return false;
    const text = String(value);
    const forbidden = [
      'visual parse unavailable',
      '[visual parse unavailable]',
      '[page',
      'page visual parse',
      'visual parse',
      'unavailable',
      '[object Object]',
      'null',
      'undefined',
    ];
    return forbidden.some((item) => text.toLowerCase().includes(item.toLowerCase()));
  }

  private async normalizeParsedImages(
    images: Array<Record<string, any> | string>,
    taskId: string | undefined,
    scope: 'question' | 'material',
  ) {
    const normalized: Array<Record<string, any>> = [];
    for (const image of images) {
      if (typeof image === 'string') {
        normalized.push({ url: image });
        continue;
      }
      const item = { ...image };
      if (item.base64 && !item.url?.startsWith?.('http')) {
        try {
          const upload = await this.uploadService.uploadBuffer(
            Buffer.from(String(item.base64), 'base64'),
            {
              filename: `${item.ref || scope}.png`,
              mimetype: 'image/png',
              prefix: `pdf-parse/${taskId || 'manual'}/${scope}`,
            },
          );
          item.url = upload.url;
          delete item.base64;
        } catch (error) {
          this.logger.warn(
            `Upload parsed image failed task=${taskId} ref=${item.ref || ''}: ${
              error instanceof Error ? error.message : String(error)
            }`,
          );
        }
      }
      item.image_role = item.image_role || this.imageRoleForParsedImage(item.role);
      item.image_order = Number.isFinite(Number(item.image_order))
        ? Number(item.image_order)
        : normalized.length + 1;
      item.insert_position = item.insert_position || 'below_stem';
      normalized.push(item);
    }
    return normalized;
  }

  private imageRoleForParsedImage(role: unknown) {
    const value = String(role || '');
    if (value === 'material') return 'material';
    if (value.startsWith('option_')) return 'option_image';
    if (['chart', 'table', 'image', 'visual', 'question_visual'].includes(value)) {
      return 'question_visual';
    }
    return 'unknown';
  }

  private async ensureImageQuestionLinks(question: Question) {
    const images = Array.isArray(question.images) ? question.images : [];
    if (!images.length) return question;
    let changed = false;
    const linked = images.map((image) => {
      if (!image || typeof image !== 'object') return image;
      const item = image as Record<string, any>;
      if (item.belongs_to_question && !item.linked_question_id) {
        changed = true;
        return {
          ...item,
          linked_question_id: question.id,
        };
      }
      return image;
    });
    if (!changed) return question;
    question.images = linked;
    return this.questionRepository.save(question);
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
