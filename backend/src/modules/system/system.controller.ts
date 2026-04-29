import { Body, Controller, Get, Param, Post, Put, UseGuards } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { Roles } from '../../common/decorators/roles.decorator';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { BatchUpdateConfigDto, UpdateConfigDto } from './dto/update-config.dto';
import { SystemService } from './system.service';

@ApiTags('System')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
@Controller('admin/system')
export class SystemController {
  constructor(private readonly systemService: SystemService) {}

  @Get('configs')
  @ApiOperation({ summary: '系统配置列表' })
  listConfigs() {
    return this.systemService.listConfigs();
  }

  @Get('configs/:key')
  @ApiOperation({ summary: '系统配置详情' })
  getConfig(@Param('key') key: string) {
    return this.systemService.getConfig(key);
  }

  @Put('configs/:key')
  @ApiOperation({ summary: '修改系统配置' })
  updateConfig(@Param('key') key: string, @Body() dto: UpdateConfigDto) {
    return this.systemService.updateConfig(key, dto);
  }

  @Post('configs/batch')
  @ApiOperation({ summary: '批量修改系统配置' })
  batchUpdate(@Body() dto: BatchUpdateConfigDto) {
    return this.systemService.batchUpdate(dto);
  }

  @Get('info')
  @ApiOperation({ summary: '系统运行信息' })
  info() {
    return this.systemService.info();
  }
}
