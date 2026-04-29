import { Controller, Get, Query, UseGuards } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { Roles } from '../../common/decorators/roles.decorator';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { AdminStatsService } from './admin-stats.service';

@ApiTags('Admin Stats')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
@Controller('admin/stats')
export class AdminStatsController {
  constructor(private readonly statsService: AdminStatsService) {}

  @Get('overview')
  @ApiOperation({ summary: '全站数据概览' })
  overview() {
    return this.statsService.overview();
  }

  @Get('trend')
  @ApiOperation({ summary: '近30天答题趋势' })
  trend() {
    return this.statsService.trend();
  }

  @Get('hot-questions')
  @ApiOperation({ summary: '题目热度排行' })
  hotQuestions(@Query() query: Record<string, unknown>) {
    return this.statsService.hotQuestions(query as any);
  }

  @Get('active-users')
  @ApiOperation({ summary: '用户活跃排行' })
  activeUsers(@Query() query: Record<string, unknown>) {
    return this.statsService.activeUsers(query as any);
  }

  @Get('banks')
  @ApiOperation({ summary: '题库使用情况' })
  banks() {
    return this.statsService.banks();
  }
}
