import { Injectable, NotFoundException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { InjectDataSource, InjectRepository } from '@nestjs/typeorm';
import axios from 'axios';
import { DataSource, Repository } from 'typeorm';
import { RedisService } from '../../common/services/redis.service';
import { BatchUpdateConfigDto, UpdateConfigDto } from './dto/update-config.dto';
import { SystemConfig, SystemConfigValueType } from './entities/system-config.entity';

@Injectable()
export class SystemService {
  constructor(
    @InjectRepository(SystemConfig)
    private readonly configRepository: Repository<SystemConfig>,
    @InjectDataSource()
    private readonly dataSource: DataSource,
    private readonly configService: ConfigService,
    private readonly redisService: RedisService,
  ) {}

  listConfigs() {
    return this.configRepository.find({ order: { key: 'ASC' } });
  }

  async getConfig(key: string) {
    const config = await this.configRepository.findOne({ where: { key } });
    if (!config) throw new NotFoundException('配置不存在');
    return config;
  }

  async updateConfig(key: string, dto: UpdateConfigDto) {
    let config = await this.configRepository.findOne({ where: { key } });
    if (!config) {
      config = this.configRepository.create({
        key,
        value_type: SystemConfigValueType.String,
      });
    }
    config.value = dto.value;
    if (typeof dto.description === 'string') config.description = dto.description;
    const saved = await this.configRepository.save(config);
    if (key.startsWith('prompt.')) {
      void this.invalidatePdfServiceCache().catch(() => undefined);
    }
    return saved;
  }

  async batchUpdate(dto: BatchUpdateConfigDto) {
    for (const item of dto.configs || []) {
      await this.updateConfig(item.key, { value: item.value });
    }
    return { updated_count: dto.configs?.length || 0 };
  }

  async info() {
    const pdfServiceUrl = this.configService.get<string>(
      'PDF_SERVICE_URL',
      'http://localhost:8001',
    );
    const [redisOk, pdfOk] = await Promise.all([
      this.redisService.ping(),
      axios
        .get(`${pdfServiceUrl}/health`, { timeout: 3000 })
        .then(() => true)
        .catch(() => false),
    ]);
    return {
      node_version: process.version,
      platform: process.platform,
      uptime_seconds: Math.floor(process.uptime()),
      memory_used_mb: Math.round(process.memoryUsage().rss / 1024 / 1024),
      db_status: this.dataSource.isInitialized ? 'connected' : 'error',
      redis_status: redisOk ? 'connected' : 'error',
      pdf_service_status: pdfOk ? 'online' : 'offline',
      env: process.env.NODE_ENV || 'development',
    };
  }

  async pdfServiceStatus() {
    const startedAt = Date.now();
    try {
      const data = await this.proxyPdfService('GET', '/status');
      return {
        ...(data as Record<string, unknown>),
        reachable: true,
        response_ms: Date.now() - startedAt,
      };
    } catch (error) {
      return {
        status: 'offline',
        reachable: false,
        response_ms: Date.now() - startedAt,
        error: error instanceof Error ? error.message : 'PDF 服务不可达',
      };
    }
  }

  async pdfServiceStats() {
    try {
      return await this.proxyPdfService('GET', '/stats');
    } catch (error) {
      return {
        today: {
          total_parsed: 0,
          total_questions: 0,
          success_count: 0,
          fail_count: 0,
          avg_questions_per_pdf: 0,
          avg_parse_seconds: 0,
        },
        session: { total_parsed: 0, total_questions: 0, ai_calls: {} },
        error: error instanceof Error ? error.message : 'PDF 服务统计不可达',
      };
    }
  }

  async testPdfParse(body: Record<string, unknown>) {
    const aiConfig = await this.getAiConfig();
    const pdfServiceUrl = this.configService.get<string>(
      'PDF_SERVICE_URL',
      'http://localhost:8001',
    );
    const token = this.configService.get<string>('PDF_SERVICE_INTERNAL_TOKEN', '');
    const response = await axios.request({
      method: 'POST',
      url: `${pdfServiceUrl}/admin/test-parse`,
      data: {
        url: body.file_url || body.url,
        pages: body.pages,
        ai_config: aiConfig,
      },
      timeout: 15 * 60 * 1000,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    return response.data;
  }

  async pdfServiceConfig() {
    const [serviceConfig, aiConfig] = await Promise.all([
      this.proxyPdfService('GET', '/admin/config', undefined, true).catch(() => ({})),
      this.getAiConfig(),
    ]);
    return {
      ...(serviceConfig as Record<string, unknown>),
      qwen_api_key_set: Boolean(aiConfig.dashscope_api_key),
      deepseek_api_key_set: Boolean(aiConfig.deepseek_api_key),
      mimo_api_key_set: Boolean(aiConfig.mimo_api_key),
      ark_api_key_set: Boolean(aiConfig.ark_api_key),
      baidu_api_key_set: Boolean(aiConfig.baidu_api_key),
      baidu_secret_key_set: Boolean(aiConfig.baidu_secret_key),
      baidu_access_token_set: Boolean(aiConfig.baidu_access_token),
      tencent_secret_id_set: Boolean(aiConfig.tencent_secret_id),
      tencent_secret_key_set: Boolean(aiConfig.tencent_secret_key),
      ai_provider_vision:
        (serviceConfig as Record<string, unknown>)?.ai_provider_vision || 'qwen_vl',
      ai_provider_text:
        (serviceConfig as Record<string, unknown>)?.ai_provider_text || 'qwen',
      backend_url:
        (serviceConfig as Record<string, unknown>)?.backend_url || 'http://localhost:3010',
      prompt_source:
        (serviceConfig as Record<string, unknown>)?.prompt_source || 'database',
      cache_ttl: (serviceConfig as Record<string, unknown>)?.cache_ttl || 300,
      commercial_ocr_enabled:
        (serviceConfig as Record<string, unknown>)?.commercial_ocr_enabled ||
        aiConfig.commercial_ocr_enabled ||
        'false',
      commercial_ocr_real_smoke:
        (serviceConfig as Record<string, unknown>)?.commercial_ocr_real_smoke ||
        aiConfig.commercial_ocr_real_smoke ||
        'false',
      pdf_parse_primary_provider:
        (serviceConfig as Record<string, unknown>)?.pdf_parse_primary_provider ||
        aiConfig.pdf_parse_primary_provider ||
        'mock_commercial_ocr',
      pdf_parse_fallback_providers:
        (serviceConfig as Record<string, unknown>)?.pdf_parse_fallback_providers ||
        aiConfig.pdf_parse_fallback_providers ||
        'local_parser,mock_commercial_ocr',
      mock_commercial_ocr_fixture_name:
        (serviceConfig as Record<string, unknown>)?.mock_commercial_ocr_fixture_name ||
        aiConfig.mock_commercial_ocr_fixture_name ||
        '',
      commercial_ocr_fixture_root:
        (serviceConfig as Record<string, unknown>)?.commercial_ocr_fixture_root ||
        aiConfig.commercial_ocr_fixture_root ||
        '',
      mock_tencent_question_split_fixture_name:
        (serviceConfig as Record<string, unknown>)?.mock_tencent_question_split_fixture_name ||
        aiConfig.mock_tencent_question_split_fixture_name ||
        '',
      mock_tencent_question_split_layout_fixture_name:
        (serviceConfig as Record<string, unknown>)?.mock_tencent_question_split_layout_fixture_name ||
        aiConfig.mock_tencent_question_split_layout_fixture_name ||
        '',
      ocr_provider_trace_enabled:
        (serviceConfig as Record<string, unknown>)?.ocr_provider_trace_enabled ||
        aiConfig.ocr_provider_trace_enabled ||
        'true',
    };
  }

  async updatePdfServiceConfig(body: Record<string, unknown>) {
    const updates: Promise<unknown>[] = [];
    if (typeof body.qwen_api_key === 'string' && body.qwen_api_key) {
      updates.push(
        this.updateConfig('DASHSCOPE_API_KEY', {
          value: body.qwen_api_key,
          description: '阿里云百炼 API Key（用于通义千问 VL/文本模型）',
        }),
      );
    }
    if (typeof body.deepseek_api_key === 'string' && body.deepseek_api_key) {
      updates.push(
        this.updateConfig('DEEPSEEK_API_KEY', {
          value: body.deepseek_api_key,
          description: 'DeepSeek API Key（用于文字结构化）',
        }),
      );
    }
    if (typeof body.mimo_api_key === 'string' && body.mimo_api_key) {
      updates.push(
        this.updateConfig('MIMO_API_KEY', {
          value: body.mimo_api_key,
          description: 'MiMo API Key（用于视觉 fallback）',
        }),
      );
    }
    if (typeof body.mimo_base_url === 'string' && body.mimo_base_url) {
      updates.push(
        this.updateConfig('MIMO_BASE_URL', {
          value: body.mimo_base_url,
          description: 'MiMo Base URL（用于视觉 fallback）',
        }),
      );
    }
    if (typeof body.mimo_model === 'string' && body.mimo_model) {
      updates.push(
        this.updateConfig('MIMO_MODEL', {
          value: body.mimo_model,
          description: 'MiMo 默认模型',
        }),
      );
    }
    if (typeof body.mimo_vision_model === 'string' && body.mimo_vision_model) {
      updates.push(
        this.updateConfig('MIMO_VISION_MODEL', {
          value: body.mimo_vision_model,
          description: 'MiMo 视觉模型',
        }),
      );
    }
    if (typeof body.ark_api_key === 'string' && body.ark_api_key) {
      updates.push(
        this.updateConfig('ARK_API_KEY', {
          value: body.ark_api_key,
          description: '火山方舟视觉 API Key',
        }),
      );
    }
    if (typeof body.ark_base_url === 'string' && body.ark_base_url) {
      updates.push(
        this.updateConfig('ARK_BASE_URL', {
          value: body.ark_base_url,
          description: '火山方舟 OpenAI-compatible Base URL',
        }),
      );
    }
    if (typeof body.ark_vision_model === 'string' && body.ark_vision_model) {
      updates.push(
        this.updateConfig('ARK_VISION_MODEL', {
          value: body.ark_vision_model,
          description: '火山方舟视觉模型或 endpoint id',
        }),
      );
    }
    if (typeof body.ark_endpoint_id === 'string' && body.ark_endpoint_id) {
      updates.push(
        this.updateConfig('ARK_ENDPOINT_ID', {
          value: body.ark_endpoint_id,
          description: '火山方舟 endpoint id',
        }),
      );
    }
    if (typeof body.ark_api_mode === 'string' && body.ark_api_mode) {
      updates.push(
        this.updateConfig('ARK_API_MODE', {
          value: body.ark_api_mode,
          description: '火山方舟 API 模式，默认 responses',
        }),
      );
    }
    if (typeof body.ark_responses_path === 'string' && body.ark_responses_path) {
      updates.push(
        this.updateConfig('ARK_RESPONSES_PATH', {
          value: body.ark_responses_path,
          description: '火山方舟 Responses API 路径',
        }),
      );
    }
    if (typeof body.vision_ai_provider_order === 'string' && body.vision_ai_provider_order) {
      updates.push(
        this.updateConfig('VISION_AI_PROVIDER_ORDER', {
          value: body.vision_ai_provider_order,
          description: '视觉 provider fallback 顺序',
        }),
      );
    }
    if (
      typeof body.vision_ai_timeout_seconds === 'number' &&
      Number.isFinite(body.vision_ai_timeout_seconds)
    ) {
      updates.push(
        this.updateConfig('VISION_AI_TIMEOUT_SECONDS', {
          value: String(body.vision_ai_timeout_seconds),
          description: '视觉理解总超时秒数',
        }),
      );
    }
    if (
      typeof body.vision_ai_provider_timeout_seconds === 'number' &&
      Number.isFinite(body.vision_ai_provider_timeout_seconds)
    ) {
      updates.push(
        this.updateConfig('VISION_AI_PROVIDER_TIMEOUT_SECONDS', {
          value: String(body.vision_ai_provider_timeout_seconds),
          description: '视觉 provider 单次超时秒数',
        }),
      );
    }
    if (
      typeof body.pdf_visual_page_timeout_seconds === 'number' &&
      Number.isFinite(body.pdf_visual_page_timeout_seconds)
    ) {
      updates.push(
        this.updateConfig('PDF_VISUAL_PAGE_TIMEOUT_SECONDS', {
          value: String(body.pdf_visual_page_timeout_seconds),
          description: '整页视觉解析超时秒数',
        }),
      );
    }
    if (
      typeof body.pdf_visual_provider_timeout_seconds === 'number' &&
      Number.isFinite(body.pdf_visual_provider_timeout_seconds)
    ) {
      updates.push(
        this.updateConfig('PDF_VISUAL_PROVIDER_TIMEOUT_SECONDS', {
          value: String(body.pdf_visual_provider_timeout_seconds),
          description: '整页视觉 provider 超时秒数',
        }),
      );
    }
    const configWrites: Array<[unknown, string, string]> = [
      [body.commercial_ocr_enabled, 'COMMERCIAL_OCR_ENABLED', 'commercial OCR 主链路开关'],
      [body.commercial_ocr_real_smoke, 'COMMERCIAL_OCR_REAL_SMOKE', 'commercial OCR 真实 smoke 开关'],
      [body.pdf_parse_primary_provider, 'PDF_PARSE_PRIMARY_PROVIDER', 'PDF 解析主 provider'],
      [body.pdf_parse_fallback_providers, 'PDF_PARSE_FALLBACK_PROVIDERS', 'PDF 解析 fallback provider 顺序'],
      [body.mock_commercial_ocr_fixture_name, 'MOCK_COMMERCIAL_OCR_FIXTURE_NAME', 'mock commercial OCR fixture'],
      [body.commercial_ocr_fixture_root, 'COMMERCIAL_OCR_FIXTURE_ROOT', 'mock commercial OCR fixture root'],
      [body.mock_tencent_question_split_fixture_name, 'MOCK_TENCENT_QUESTION_SPLIT_FIXTURE_NAME', 'mock tencent QuestionSplit fixture'],
      [body.mock_tencent_question_split_layout_fixture_name, 'MOCK_TENCENT_QUESTION_SPLIT_LAYOUT_FIXTURE_NAME', 'mock tencent QuestionSplitLayout fixture'],
      [body.ocr_provider_trace_enabled, 'OCR_PROVIDER_TRACE_ENABLED', 'provider trace 开关'],
      [body.baidu_api_key, 'BAIDU_API_KEY', '百度 OCR API Key'],
      [body.baidu_secret_key, 'BAIDU_SECRET_KEY', '百度 OCR Secret Key'],
      [body.baidu_access_token, 'BAIDU_ACCESS_TOKEN', '百度 OCR Access Token'],
      [body.baidu_ocr_endpoint, 'BAIDU_OCR_ENDPOINT', '百度 OCR endpoint'],
      [body.baidu_ocr_timeout_ms, 'BAIDU_OCR_TIMEOUT_MS', '百度 OCR timeout(ms)'],
      [body.tencent_secret_id, 'TENCENT_SECRET_ID', '腾讯 OCR SecretId'],
      [body.tencent_secret_key, 'TENCENT_SECRET_KEY', '腾讯 OCR SecretKey'],
      [body.tencent_region, 'TENCENT_REGION', '腾讯 OCR region'],
      [body.tencent_ocr_endpoint, 'TENCENT_OCR_ENDPOINT', '腾讯 OCR endpoint'],
      [body.tencent_ocr_version, 'TENCENT_OCR_VERSION', '腾讯 OCR version'],
      [body.tencent_ocr_timeout_ms, 'TENCENT_OCR_TIMEOUT_MS', '腾讯 OCR timeout(ms)'],
      [body.tencent_ocr_use_new_model, 'TENCENT_OCR_USE_NEW_MODEL', '腾讯 OCR UseNewModel 开关'],
      [body.tencent_ocr_enable_image_crop, 'TENCENT_OCR_ENABLE_IMAGE_CROP', '腾讯 OCR EnableImageCrop 开关'],
      [body.tencent_ocr_enable_only_detect_border, 'TENCENT_OCR_ENABLE_ONLY_DETECT_BORDER', '腾讯 OCR EnableOnlyDetectBorder 开关'],
      [body.tencent_ocr_real_smoke, 'TENCENT_OCR_REAL_SMOKE', '腾讯 OCR 真实 smoke 开关'],
    ];
    for (const [value, key, description] of configWrites) {
      if (typeof value === 'string' && value !== '') {
        updates.push(this.updateConfig(key, { value, description }));
      } else if (typeof value === 'boolean') {
        updates.push(this.updateConfig(key, { value: String(value), description }));
      } else if (typeof value === 'number' && Number.isFinite(value)) {
        updates.push(this.updateConfig(key, { value: String(value), description }));
      }
    }
    await Promise.all(updates);
    return this.proxyPdfService('PUT', '/admin/config', body, true);
  }

  invalidatePdfServiceCache() {
    return this.proxyPdfService('POST', '/admin/cache/invalidate', {}, true);
  }

  async proxyPdfService(
    method: 'GET' | 'POST' | 'PUT',
    path: string,
    data?: unknown,
    internalAuth = false,
  ) {
    const pdfServiceUrl = this.configService.get<string>(
      'PDF_SERVICE_URL',
      'http://localhost:8001',
    );
    const token = this.configService.get<string>('PDF_SERVICE_INTERNAL_TOKEN', '');
    const response = await axios.request({
      method,
      url: `${pdfServiceUrl}${path}`,
      data,
      timeout: path.includes('test-parse') ? 5 * 60 * 1000 : 10000,
      headers: internalAuth && token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    return response.data;
  }

  private async getAiConfig() {
    const configs = await this.configRepository.find({
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
        { key: 'COMMERCIAL_OCR_ENABLED' },
        { key: 'COMMERCIAL_OCR_REAL_SMOKE' },
        { key: 'PDF_PARSE_PRIMARY_PROVIDER' },
        { key: 'PDF_PARSE_FALLBACK_PROVIDERS' },
        { key: 'MOCK_COMMERCIAL_OCR_FIXTURE_NAME' },
        { key: 'MOCK_TENCENT_QUESTION_SPLIT_FIXTURE_NAME' },
        { key: 'MOCK_TENCENT_QUESTION_SPLIT_LAYOUT_FIXTURE_NAME' },
        { key: 'OCR_PROVIDER_TRACE_ENABLED' },
        { key: 'BAIDU_API_KEY' },
        { key: 'BAIDU_SECRET_KEY' },
        { key: 'BAIDU_ACCESS_TOKEN' },
        { key: 'BAIDU_OCR_ENDPOINT' },
        { key: 'BAIDU_OCR_TIMEOUT_MS' },
        { key: 'TENCENT_SECRET_ID' },
        { key: 'TENCENT_SECRET_KEY' },
        { key: 'TENCENT_REGION' },
        { key: 'TENCENT_OCR_ENDPOINT' },
        { key: 'TENCENT_OCR_VERSION' },
        { key: 'TENCENT_OCR_TIMEOUT_MS' },
        { key: 'TENCENT_OCR_USE_NEW_MODEL' },
        { key: 'TENCENT_OCR_ENABLE_IMAGE_CROP' },
        { key: 'TENCENT_OCR_ENABLE_ONLY_DETECT_BORDER' },
        { key: 'TENCENT_OCR_REAL_SMOKE' },
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
        visual_model: read('AI_VISUAL_MODEL', 'qwen3-vl-plus'),
        text_api_key: read('AI_TEXT_API_KEY') || read('DEEPSEEK_API_KEY') || read('DASHSCOPE_API_KEY'),
        text_base_url:
          read('AI_TEXT_BASE_URL') ||
          read('DEEPSEEK_BASE_URL') ||
          read('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
        text_model: read('AI_TEXT_MODEL') || read('DEEPSEEK_MODEL') || 'qwen-plus',
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
        commercial_ocr_enabled: read('COMMERCIAL_OCR_ENABLED', 'false'),
        commercial_ocr_real_smoke: read('COMMERCIAL_OCR_REAL_SMOKE', 'false'),
        pdf_parse_primary_provider: read('PDF_PARSE_PRIMARY_PROVIDER', 'mock_commercial_ocr'),
        pdf_parse_fallback_providers: read(
          'PDF_PARSE_FALLBACK_PROVIDERS',
          'local_parser,mock_commercial_ocr',
        ),
        mock_commercial_ocr_fixture_name: read('MOCK_COMMERCIAL_OCR_FIXTURE_NAME'),
        commercial_ocr_fixture_root: read('COMMERCIAL_OCR_FIXTURE_ROOT'),
        mock_tencent_question_split_fixture_name: read(
          'MOCK_TENCENT_QUESTION_SPLIT_FIXTURE_NAME',
        ),
        mock_tencent_question_split_layout_fixture_name: read(
          'MOCK_TENCENT_QUESTION_SPLIT_LAYOUT_FIXTURE_NAME',
        ),
        ocr_provider_trace_enabled: read('OCR_PROVIDER_TRACE_ENABLED', 'true'),
        baidu_api_key: read('BAIDU_API_KEY'),
        baidu_secret_key: read('BAIDU_SECRET_KEY'),
        baidu_access_token: read('BAIDU_ACCESS_TOKEN'),
        baidu_ocr_endpoint: read('BAIDU_OCR_ENDPOINT'),
        baidu_ocr_timeout_ms: read('BAIDU_OCR_TIMEOUT_MS', '60000'),
        tencent_secret_id: read('TENCENT_SECRET_ID'),
        tencent_secret_key: read('TENCENT_SECRET_KEY'),
        tencent_region: read('TENCENT_REGION', 'ap-guangzhou'),
        tencent_ocr_endpoint: read('TENCENT_OCR_ENDPOINT', 'https://ocr.tencentcloudapi.com'),
        tencent_ocr_version: read('TENCENT_OCR_VERSION', '2018-11-19'),
        tencent_ocr_timeout_ms: read('TENCENT_OCR_TIMEOUT_MS', '60000'),
        tencent_ocr_use_new_model: read('TENCENT_OCR_USE_NEW_MODEL', 'false'),
        tencent_ocr_enable_image_crop: read('TENCENT_OCR_ENABLE_IMAGE_CROP', 'false'),
        tencent_ocr_enable_only_detect_border: read(
          'TENCENT_OCR_ENABLE_ONLY_DETECT_BORDER',
          'false',
        ),
        tencent_ocr_real_smoke: read('TENCENT_OCR_REAL_SMOKE', 'false'),
      }).filter(([, value]) => Boolean(value)),
    );
  }
}
