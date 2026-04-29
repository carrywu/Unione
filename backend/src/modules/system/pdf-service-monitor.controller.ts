import { Body, Controller, Get, Post, Put, UseGuards } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { Roles } from '../../common/decorators/roles.decorator';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { SystemService } from './system.service';

@ApiTags('PDF Service Monitor')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
@Controller('admin/pdf-service')
export class PdfServiceMonitorController {
  constructor(private readonly systemService: SystemService) {}

  @Get('status')
  @ApiOperation({ summary: 'PDF 服务运行状态' })
  status() {
    return this.systemService.pdfServiceStatus();
  }

  @Get('stats')
  @ApiOperation({ summary: 'PDF 服务解析统计' })
  stats() {
    return this.systemService.pdfServiceStats();
  }

  @Get('config')
  @ApiOperation({ summary: 'PDF 服务运行配置' })
  config() {
    return this.systemService.pdfServiceConfig();
  }

  @Put('config')
  @ApiOperation({ summary: '热更新 PDF 服务配置' })
  updateConfig(@Body() body: Record<string, unknown>) {
    return this.systemService.updatePdfServiceConfig(body);
  }

  @Post('test-parse')
  @ApiOperation({ summary: 'PDF 服务测试解析（不入库）' })
  testParse(@Body() body: Record<string, unknown>) {
    return this.systemService.testPdfParse(body);
  }

  @Post('cache-invalidate')
  @ApiOperation({ summary: '清除 PDF 服务提示词缓存' })
  invalidateCache() {
    return this.systemService.invalidatePdfServiceCache();
  }
}
