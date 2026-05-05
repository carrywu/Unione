import { Controller, Get } from '@nestjs/common';
import { ApiOperation, ApiTags } from '@nestjs/swagger';
import { SystemService } from '../system/system.service';

@ApiTags('Health')
@Controller('api')
export class HealthController {
  constructor(private readonly systemService: SystemService) {}

  @Get('health')
  @ApiOperation({ summary: '公开健康探针（无需认证）' })
  async health() {
    const info = await this.systemService.info();
    const healthy =
      info.db_status === 'connected' &&
      info.redis_status === 'connected';
    return {
      status: healthy ? 'ok' : 'degraded',
      timestamp: new Date().toISOString(),
      ...info,
    };
  }
}
