import { Body, Controller, Delete, Get, Param, Post, Put, Query, UseGuards } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { PaginationDto } from '../../common/dto/pagination.dto';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { BatchSubmitRecordDto } from './dto/batch-submit-record.dto';
import { ClearWrongDto, QueryWrongDto, WrongPracticeDto } from './dto/query-wrong.dto';
import { SubmitRecordDto } from './dto/submit-record.dto';
import { RecordService } from './record.service';

@ApiTags('Records')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('api/records')
export class RecordController {
  constructor(private readonly recordService: RecordService) {}

  @Post('submit')
  @ApiOperation({ summary: '提交答题记录' })
  submit(@CurrentUser('sub') userId: string, @Body() dto: SubmitRecordDto) {
    return this.recordService.submit(userId, dto);
  }

  @Post('batch-submit')
  @ApiOperation({ summary: '批量提交答题记录' })
  batchSubmit(
    @CurrentUser('sub') userId: string,
    @Body() dto: BatchSubmitRecordDto,
  ) {
    return this.recordService.batchSubmit(userId, dto);
  }

  @Get('history')
  @ApiOperation({ summary: '答题历史' })
  history(@CurrentUser('sub') userId: string, @Query() query: PaginationDto) {
    return this.recordService.history(userId, query);
  }

  @Get('wrong')
  @ApiOperation({ summary: '错题本' })
  wrong(@CurrentUser('sub') userId: string, @Query() query: QueryWrongDto) {
    return this.recordService.wrong(userId, query);
  }

  @Get('stats')
  @ApiOperation({ summary: '答题统计' })
  stats(@CurrentUser('sub') userId: string) {
    return this.recordService.stats(userId);
  }

  @Delete('wrong/:questionId')
  @ApiOperation({ summary: '从错题本移除' })
  removeWrong(
    @CurrentUser('sub') userId: string,
    @Param('questionId') questionId: string,
  ) {
    return this.recordService.removeWrong(userId, questionId);
  }
}

@ApiTags('Wrong')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('api/wrong')
export class WrongController {
  constructor(private readonly recordService: RecordService) {}

  @Put(':id/master')
  @ApiOperation({ summary: '标记错题已掌握' })
  master(@CurrentUser('sub') userId: string, @Param('id') id: string) {
    return this.recordService.masterWrong(userId, id);
  }

  @Put(':id/unmaster')
  @ApiOperation({ summary: '取消错题掌握' })
  unmaster(@CurrentUser('sub') userId: string, @Param('id') id: string) {
    return this.recordService.unmasterWrong(userId, id);
  }

  @Delete('clear')
  @ApiOperation({ summary: '清空错题本' })
  clear(@CurrentUser('sub') userId: string, @Query() query: ClearWrongDto) {
    return this.recordService.clearWrong(userId, query);
  }

  @Get('practice')
  @ApiOperation({ summary: '错题随机练习' })
  practice(
    @CurrentUser('sub') userId: string,
    @Query() query: WrongPracticeDto,
  ) {
    return this.recordService.wrongPractice(userId, query);
  }

  @Get('stats')
  @ApiOperation({ summary: '错题本统计' })
  wrongStats(@CurrentUser('sub') userId: string) {
    return this.recordService.wrongStats(userId);
  }
}

@ApiTags('Stats')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('api/stats')
export class StatsController {
  constructor(private readonly recordService: RecordService) {}

  @Get('overview')
  @ApiOperation({ summary: '用户学习概览' })
  overview(@CurrentUser('sub') userId: string) {
    return this.recordService.stats(userId);
  }

  @Get('calendar')
  @ApiOperation({ summary: '学习日历' })
  calendar(@CurrentUser('sub') userId: string) {
    return this.recordService.calendar(userId);
  }

  @Get('streak')
  @ApiOperation({ summary: '连续学习天数' })
  streak(@CurrentUser('sub') userId: string) {
    return this.recordService.streak(userId);
  }

  @Get('weakness')
  @ApiOperation({ summary: '薄弱题本分析' })
  weakness(@CurrentUser('sub') userId: string) {
    return this.recordService.weakness(userId);
  }
}
