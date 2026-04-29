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
import { Response } from 'express';
import { Repository } from 'typeorm';
import { QuestionBank } from '../bank/entities/question-bank.entity';
import { Material } from '../question/entities/material.entity';
import { SystemConfig } from '../system/entities/system-config.entity';
import { UploadService } from '../upload/upload.service';
import {
  Question,
  QuestionStatus,
  QuestionType,
} from '../question/entities/question.entity';
import { ParsePdfDto } from './dto/parse-pdf.dto';
import { OcrRegionDto, OcrRegionMode } from './dto/ocr-region.dto';
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
        pages: typeof body.pages === 'string' ? body.pages : '9-14',
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
          }),
        });
        await this.refreshBankTotal(task.bank_id);
        this.logger.log(
          `Done parse task id=${task.id} questions=${questions.length}`,
        );
      } else {
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
      this.callbackMaterialMaps.delete(taskId);
      await this.refreshBankTotal(task.bank_id);
      return { status: ParseTaskStatus.Failed, total_count: totalCount };
    }
    await this.taskRepository.update(task.id, {
      status: ParseTaskStatus.Done,
      progress: 100,
      total_count: totalCount,
      done_count: doneCount,
      result_summary: JSON.stringify({
        stats: body.stats || {},
        detection: body.detection || body.stats?.detection || null,
        delivery: 'callback_batches',
      }),
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
    });
  }

  private async clearPreviousTaskResults(taskId: string) {
    await this.questionRepository.delete({ parse_task_id: taskId });
    await this.materialRepository.delete({ parse_task_id: taskId });
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
    const saved: Question[] = [];
    for (const raw of questions) {
      const material = raw.material_id ? materials.get(raw.material_id) : null;
      const images = await this.normalizeParsedImages(raw.images || [], taskId, 'question');
      const options = raw.options || {};
      const entity = this.questionRepository.create({
        bank_id: bankId,
        parse_task_id: taskId,
        material_id: material?.id,
        index_num: this.toNumber(raw.index ?? raw.index_num, 0),
        type:
          raw.type === QuestionType.Judge
            ? QuestionType.Judge
            : QuestionType.Single,
        content: this.cleanParsedText(raw.content),
        option_a: options.A || options.a || raw.option_a || null,
        option_b: options.B || options.b || raw.option_b || null,
        option_c: options.C || options.c || raw.option_c || null,
        option_d: options.D || options.d || raw.option_d || null,
        answer: raw.answer || null,
        analysis: raw.analysis || null,
        images,
        ai_image_desc: images
          .map((image) => image.ai_desc)
          .filter(Boolean)
          .join('\n'),
        page_num: this.toOptionalNumber(
          raw.page_num ?? raw.page ?? raw.pageNumber,
        ),
        page_range: this.toNumberArray(raw.page_range ?? raw.pageRange),
        source_page_start: this.toOptionalNumber(
          raw.source_page_start ?? raw.sourcePageStart,
        ),
        source_page_end: this.toOptionalNumber(
          raw.source_page_end ?? raw.sourcePageEnd,
        ),
        source_bbox: this.toNumberArray(raw.source_bbox ?? raw.sourceBbox),
        source_anchor_text: raw.source_anchor_text || raw.sourceAnchorText || null,
        source_confidence: this.toOptionalNumber(
          raw.source_confidence ?? raw.sourceConfidence,
        ),
        image_refs: this.toStringArray(raw.image_refs ?? raw.imageRefs),
        source: raw.source || raw.parse_source || null,
        raw_text: raw.raw_text || raw.rawText || null,
        parse_confidence: this.toOptionalNumber(
          raw.parse_confidence ?? raw.confidence,
        ),
        parse_warnings: this.toStringArray(
          raw.parse_warnings ?? raw.parseWarnings,
        ),
        status: QuestionStatus.Draft,
        needs_review: Boolean(raw.needs_review || raw.parse_warnings?.length),
      });
      const existing = await this.questionRepository.findOne({
        where: { parse_task_id: taskId, index_num: entity.index_num },
      });
      if (existing) {
        Object.assign(existing, entity, { id: existing.id });
        saved.push(await this.questionRepository.save(existing));
      } else {
        saved.push(await this.questionRepository.save(entity));
      }
    }
    return saved;
  }

  private async refreshBankTotal(bankId: string) {
    const total = await this.questionRepository.count({
      where: { bank_id: bankId },
    });
    await this.bankRepository.update(bankId, { total_count: total });
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
      .filter((line) => !['【', '】'].includes(line.trim()))
      .join('\n')
      .trim()
      .replace(/^】+/, '')
      .replace(/【+$/, '')
      .trim();
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
      normalized.push(item);
    }
    return normalized;
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
