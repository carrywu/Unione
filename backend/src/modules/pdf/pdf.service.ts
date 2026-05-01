import {
  BadRequestException,
  Injectable,
  Logger,
  NotFoundException,
} from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { ConfigService } from '@nestjs/config';
import { InjectRepository } from '@nestjs/typeorm';
import axios from 'axios';
import { EventEmitter } from 'events';
import { Response } from 'express';
import { Repository } from 'typeorm';
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

    return {
      status: task.status,
      progress: task.progress,
      total_count: task.total_count,
      done_count: task.done_count,
      result_summary: task.result_summary,
      error: task.error,
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
      ![ParseTaskStatus.Failed, ParseTaskStatus.Paused].includes(
        task.status as ParseTaskStatus,
      )
    ) {
      throw new BadRequestException('只有失败或已暂停的任务才能重试');
    }
    await this.taskRepository.update(task.id, {
      status: ParseTaskStatus.Pending,
      progress: 0,
      error: null,
      total_count: 0,
      done_count: 0,
      attempt: task.attempt + 1,
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
    if (!debugPayload && !finalPreviewPayload && !aiAuditResults) {
      throw new NotFoundException('AI 预审核调试产物不存在');
    }
    return {
      taskId: task.id,
      bankId: task.bank_id,
      status: task.status,
      debug_dir: debugDir,
      qwen_vl_enabled: Boolean(debugPayload?.qwen_vl_enabled),
      qwen_vl_call_count: Number(debugPayload?.qwen_vl_call_count_after || 0),
      final_verdict: debugPayload?.final_verdict || null,
      final_preview_payload: finalPreviewPayload || debugPayload?.final_preview_payload || null,
      final_questions: finalQuestions || debugPayload?.final_questions_after_audit || [],
      ai_audit_results: aiAuditResults || debugPayload?.ai_audit_results || [],
      page_understanding: pageUnderstanding || debugPayload?.page_understanding || [],
      semantic_groups: semanticGroups || debugPayload?.semantic_groups || [],
      recrop_plan: recropPlan || debugPayload?.recrop_plan || [],
      stage_counts: stageCounts || debugPayload?.stage_counts || null,
      first_failed_stage: firstFailedStage || debugPayload?.first_failed_stage || null,
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
      },
    };
  }

  async getPaperCandidates(taskId: string) {
    const task = await this.taskRepository.findOne({ where: { id: taskId } });
    if (!task) throw new NotFoundException('解析任务不存在');

    const debug = await this.getAiPreauditDebug(taskId);
    const previewQuestions = Array.isArray(debug.final_preview_payload?.questions)
      ? debug.final_preview_payload.questions
      : [];
    const auditResults = Array.isArray(debug.ai_audit_results)
      ? debug.ai_audit_results
      : [];
    const auditsByNo = new Map<string, Record<string, any>>();
    auditResults.forEach((audit, index) => {
      const key = this.paperCandidateQuestionKey(audit?.question_no, index);
      auditsByNo.set(key, audit);
    });

    const questions = previewQuestions.map((question, index) => {
      const questionNo = question?.question_no ?? null;
      const audit =
        auditsByNo.get(this.paperCandidateQuestionKey(questionNo, index)) ||
        auditResults[index] ||
        {};
      return this.buildPaperCandidate(task, question || {}, audit || {}, index, debug);
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
      ].filter(Boolean),
    };
    const payload = {
      taskId: task.id,
      bankId: task.bank_id,
      status: task.status,
      debug_dir: debug.debug_dir,
      provider: this.firstNonEmptyProvider(debug),
      model: this.firstNonEmptyModel(debug),
      summary,
      diagnostics,
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
      },
    };
    await this.writePaperCandidateArtifact(task.id, payload);
    return payload;
  }

  async createDraftPaper(body: Record<string, unknown>) {
    const sourceTaskId = String(body.source_task_id || body.taskId || '').trim();
    if (!sourceTaskId) throw new BadRequestException('source_task_id 必填');
    const candidates = await this.getPaperCandidates(sourceTaskId);
    const bodyQuestions = Array.isArray(body.questions)
      ? (body.questions as Array<Record<string, any>>)
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
    const sections = this.normalizeDraftSections(
      body.sections || existing.sections,
      Array.isArray(body.questions) ? (body.questions as Array<Record<string, any>>) : existing.questions,
    );
    const questions = this.normalizeDraftQuestions(
      Array.isArray(body.questions) ? (body.questions as Array<Record<string, any>>) : existing.questions,
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

  private paperCandidateQuestionKey(questionNo: unknown, index: number) {
    return `${questionNo ?? `idx-${index}`}`;
  }

  private buildPaperCandidate(
    task: ParseTask,
    question: Record<string, any>,
    audit: Record<string, any>,
    index: number,
    debug: Record<string, any>,
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
    const sourcePageRefs = Array.isArray(question.source_page_refs)
      ? question.source_page_refs
      : [];
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
    const sourceReview = this.paperCandidateManualReviewDecision({
      riskFlags,
      stem,
      sourcePageRefs,
      sourceBbox,
      sourceTextSpan,
      semanticGroup,
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
        riskFlags.includes('need_manual_fix'),
    );
    const cannotReasons = [
      stemMissing ? '题干缺失或包含占位文本' : '',
      optionMissing.length ? `选项缺失: ${optionMissing.join(',')}` : '',
      imageMissing ? '图表题图片或图表预览缺失' : '',
      auditFailed ? `AI 预审核失败: ${this.safeDisplayText(audit.ai_audit_summary, '未给出摘要')}` : '',
      auditWarning && sourceReview.manualReviewable ? 'AI 预审核 warning，需人工核验原卷后才可强制加入' : '',
      !sourceReview.manualReviewable ? sourceReview.missingContextReason : '',
      riskFlags.includes('chart_title_missing_or_unlocalized') ? '图表标题缺失或未定位' : '',
      riskFlags.includes('table_header_missing_or_unlocalized') ? '表头缺失或未定位' : '',
    ].filter(Boolean);
    const canAdd = !cannotReasons.length && aiStatus === 'passed' && !needManualFix && sourceReview.manualReviewable;
    const manualForceAddAllowed = auditWarning && sourceReview.manualReviewable && !canAdd;

    return {
      candidate_id: `${task.id}:${questionNo ?? index + 1}`,
      question_no: questionNo,
      stem: stem || null,
      options,
      answer_suggestion: audit.answer_suggestion || question.answer_suggestion || question.ai_candidate_answer || null,
      answer_confidence: audit.answer_confidence ?? question.answer_confidence ?? null,
      answer_unknown_reason:
        audit.answer_unknown_reason ||
        question.answer_unknown_reason ||
        (audit.answer_suggestion || question.answer_suggestion ? null : '模型未给出可验证答案建议'),
      analysis_suggestion:
        audit.analysis_suggestion ||
        question.analysis_suggestion ||
        question.ai_candidate_analysis ||
        null,
      analysis_confidence: audit.analysis_confidence ?? question.analysis_confidence ?? null,
      analysis_unknown_reason:
        audit.analysis_unknown_reason ||
        question.analysis_unknown_reason ||
        (audit.analysis_suggestion || question.analysis_suggestion ? null : '模型未给出可验证解析建议'),
      visual_assets: visualAssets,
      preview_image_path: question.preview_image_path || null,
      source_page_refs: sourcePageRefs,
      source_bbox: sourceBbox,
      source_text_span: sourceTextSpan,
      visual_parse_status: visualStatus,
      ai_audit_status: aiStatus,
      ai_audit_verdict: audit.ai_audit_verdict || question.ai_audit_verdict || null,
      ai_audit_summary: audit.ai_audit_summary || question.ai_audit_summary || null,
      risk_flags: riskFlags,
      need_manual_fix: needManualFix,
      can_add_to_paper: canAdd,
      cannot_add_reason: canAdd ? null : cannotReasons.join('；') || '未通过自动入卷规则',
      manual_review_status: sourceReview.status,
      manualReviewable: sourceReview.manualReviewable,
      manualForceAddAllowed,
      missingContextReason: sourceReview.manualReviewable ? null : sourceReview.missingContextReason,
      recommendedAction: sourceReview.recommendedAction,
      source_locator_available: false,
      source_artifacts_refs: {
        ...(question.source_artifacts_refs || {}),
        ...(debug.artifact_refs || {}),
      },
    };
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

  private paperCandidateManualReviewDecision(input: {
    riskFlags: string[];
    stem: string;
    sourcePageRefs: unknown[];
    sourceBbox: number[] | null;
    sourceTextSpan: string | null;
    semanticGroup: Record<string, any> | null;
  }) {
    const riskText = input.riskFlags.join(' ');
    const materialDependent = this.isMaterialDependentCandidate(input.stem, input.riskFlags);
    const hasMaterialEvidence = this.hasMaterialEvidence(input.semanticGroup);
    const hasSourcePage = input.sourcePageRefs.length > 0;
    const hasSourceEvidence = Boolean(input.sourceBbox || input.sourceTextSpan);
    const sourceLocatorMissing = true;
    const extraRiskFlags = new Set<string>();

    if (!hasSourcePage) extraRiskFlags.add('source_page_missing');
    if (!hasSourceEvidence) extraRiskFlags.add('source_unverified');
    extraRiskFlags.add('paper_review_original_pdf_locator_missing');

    const missingPreviousPage =
      /partial_pdf_context|missing_previous_page_context|question_cross_page/i.test(riskText);
    const questionNotFound = /question_not_found_in_pdf/i.test(riskText);
    const sourceUnverified =
      /source_unverified|paper_review_original_pdf_locator_missing/i.test(riskText) ||
      !hasSourcePage ||
      !hasSourceEvidence ||
      sourceLocatorMissing;
    const missingMaterial =
      materialDependent &&
      (!hasMaterialEvidence ||
        /shared_material_missing|material_group_unbound|semantic_visual_incomplete|缺少.*(?:材料|图表|数据)/i.test(riskText));

    if (missingMaterial) {
      extraRiskFlags.add('shared_material_missing');
      extraRiskFlags.add('material_group_unbound');
      extraRiskFlags.add('semantic_visual_incomplete');
      extraRiskFlags.add('partial_pdf_context');
      extraRiskFlags.add('missing_previous_page_context');
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
        missingContextReason: '无法人工核验：资料分析题缺少材料组或图表证据，当前 PDF 片段无法核验',
        recommendedAction: '补齐上一页重新识别或使用完整 PDF 重新解析',
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
      candidate_id: String(item.candidate_id || item.id || `candidate-${index + 1}`),
      question_no: item.question_no ?? null,
      stem: this.safeDisplayText(item.stem, ''),
      options: this.normalizeCandidateOptions(item.options),
      answer_suggestion: item.answer_suggestion || null,
      analysis_suggestion: item.analysis_suggestion || null,
      preview_image_path: item.preview_image_path || null,
      visual_assets: Array.isArray(item.visual_assets) ? item.visual_assets : [],
      ai_audit_status: this.safeDisplayText(item.ai_audit_status, 'unknown'),
      risk_flags: this.toStringArray(item.risk_flags),
      need_manual_fix: Boolean(item.need_manual_fix),
      can_add_to_paper: Boolean(item.can_add_to_paper),
      cannot_add_reason: item.cannot_add_reason || null,
      manual_review_status: item.manual_review_status || null,
      manualReviewable: Boolean(item.manualReviewable),
      manualForceAddAllowed: Boolean(item.manualForceAddAllowed),
      missingContextReason: item.missingContextReason || null,
      recommendedAction: item.recommendedAction || null,
      section_id: String(item.section_id || defaultSectionId),
      score: Number(item.score || 1),
      order: Number(item.order || index + 1),
      source_page_refs: Array.isArray(item.source_page_refs) ? item.source_page_refs : [],
    }));
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

    try {
      this.logger.log(`Start parse task id=${task.id} bank=${task.bank_id}`);
      await this.taskRepository.update(task.id, {
        status: ParseTaskStatus.Processing,
        progress: 10,
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
          ai_config: await this.getAiConfig(),
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
          result_summary: JSON.stringify({
            stats: result.stats || {},
            detection: result.detection || result.stats?.detection || null,
            delivery: 'direct_response',
            debug_file: this.taskAiPreauditDebugFiles.get(task.id) || null,
            dedupe: this.taskQuestionDedupeStats.get(task.id) || null,
          }),
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
        await this.taskRepository.update(task.id, {
          status: ParseTaskStatus.Done,
          progress: 100,
          total_count: Number(result.questions_count || savedCount || 0),
          done_count: Number(result.questions_count || savedCount || 0),
          result_summary: JSON.stringify({
            stats: result.stats || {},
            detection: result.detection || result.stats?.detection || null,
            delivery: 'callback_batches',
            debug_file: this.taskAiPreauditDebugFiles.get(task.id) || null,
            dedupe: this.taskQuestionDedupeStats.get(task.id) || null,
          }),
        });
        await this.writeAiPreauditDebugArtifacts(task, {
          source: 'callback_batches',
          pageCount: Number(result?.stats?.pages_count || 0),
          stats: result.stats || {},
          detection: result.detection || result.stats?.detection || null,
          warnings: result.warnings || result.stats?.warnings || [],
          totalCount: Number(result.questions_count || savedCount || 0),
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
      const message = this.resolveErrorMessage(error);
      this.logger.error(
        `Failed parse task id=${task.id} message=${message}`,
        error instanceof Error ? error.stack : undefined,
      );
      await this.taskRepository.update(task.id, {
        status: ParseTaskStatus.Failed,
        progress: 100,
        error: message,
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
    if (task.status === ParseTaskStatus.Paused)
      return { ignored: true, reason: 'task paused' };

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
    if (task.status === ParseTaskStatus.Paused)
      return { ignored: true, reason: 'task paused' };

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
    if (task.status === ParseTaskStatus.Paused)
      return { ignored: true, reason: 'task paused' };

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
      result_summary: JSON.stringify({
        stats: body.stats || {},
        detection: body.detection || body.stats?.detection || null,
        delivery: 'callback_batches',
        debug_file: this.taskAiPreauditDebugFiles.get(task.id) || null,
        dedupe: this.taskQuestionDedupeStats.get(task.id) || null,
      }),
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
    await this.taskRepository.update(taskId, {
      status: ParseTaskStatus.Failed,
      progress: 100,
      total_count: 0,
      done_count: 0,
      error: '未解析到题目',
      result_summary: JSON.stringify({
        ...summary,
        error: summary.error || '未解析到题目',
        warning: 'zero_questions_extracted',
      }),
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
        { key: 'MIMO_API_KEY' },
        { key: 'MIMO_BASE_URL' },
        { key: 'MIMO_MODEL' },
        { key: 'MIMO_VISION_MODEL' },
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
      mimo_api_key: read('MIMO_API_KEY'),
      mimo_base_url: read('MIMO_BASE_URL', 'https://token-plan-cn.xiaomimimo.com/v1'),
      mimo_model: read('MIMO_MODEL', 'mimo-v2.5'),
      mimo_vision_model: read('MIMO_VISION_MODEL', 'mimo-v2.5'),
      header_footer_blacklist: read('PDF_HEADER_FOOTER_BLACKLIST'),
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
        source_anchor_text: source.source_anchor_text || source.sourceAnchorText || null,
        source_confidence: this.toOptionalNumber(
          source.source_confidence ?? source.sourceConfidence,
        ),
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
        source_page_refs: [],
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
      source_anchor_text: question.source_anchor_text,
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
