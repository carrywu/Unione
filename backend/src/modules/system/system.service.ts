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
    return this.proxyPdfService(
      'POST',
      '/admin/test-parse',
      {
        url: body.file_url || body.url,
        pages: body.pages,
        ai_config: aiConfig,
      },
      true,
    );
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
      ai_provider_vision:
        (serviceConfig as Record<string, unknown>)?.ai_provider_vision || 'qwen_vl',
      ai_provider_text:
        (serviceConfig as Record<string, unknown>)?.ai_provider_text || 'qwen',
      backend_url:
        (serviceConfig as Record<string, unknown>)?.backend_url || 'http://localhost:3010',
      prompt_source:
        (serviceConfig as Record<string, unknown>)?.prompt_source || 'database',
      cache_ttl: (serviceConfig as Record<string, unknown>)?.cache_ttl || 300,
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
        text_api_key: read('AI_TEXT_API_KEY') || read('DEEPSEEK_API_KEY') || read('DASHSCOPE_API_KEY'),
        text_base_url:
          read('AI_TEXT_BASE_URL') ||
          read('DEEPSEEK_BASE_URL') ||
          read('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
        text_model: read('AI_TEXT_MODEL') || read('DEEPSEEK_MODEL') || 'qwen-plus',
        deepseek_api_key: read('DEEPSEEK_API_KEY'),
        deepseek_base_url: read('DEEPSEEK_BASE_URL'),
        deepseek_model: read('DEEPSEEK_MODEL'),
      }).filter(([, value]) => Boolean(value)),
    );
  }
}
