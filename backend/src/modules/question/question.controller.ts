import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Post,
  Put,
  Query,
  UseGuards,
} from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { Roles } from '../../common/decorators/roles.decorator';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { BatchPublishDto } from './dto/batch-publish.dto';
import { BatchDeleteQuestionDto } from './dto/batch-delete-question.dto';
import { CreateQuestionDto } from './dto/create-question.dto';
import { QueryQuestionDto } from './dto/query-question.dto';
import { UpdateQuestionDto } from './dto/update-question.dto';
import { QuestionService } from './question.service';

@ApiTags('Questions')
@Controller('api/questions')
export class ApiQuestionController {
  constructor(private readonly questionService: QuestionService) {}

  @Get()
  @ApiOperation({ summary: '用户端题目列表' })
  list(@Query() query: QueryQuestionDto) {
    return this.questionService.listPublished(query);
  }

  @Get(':id/answer')
  @ApiBearerAuth()
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: '获取题目答案和解析' })
  answer(@Param('id') id: string, @CurrentUser('sub') userId: string) {
    return this.questionService.getAnswer(id, userId);
  }
}

@ApiTags('Admin Questions')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
@Controller('admin/questions')
export class AdminQuestionController {
  constructor(private readonly questionService: QuestionService) {}

  @Get()
  @ApiOperation({ summary: '管理端题目列表' })
  list(@Query() query: QueryQuestionDto) {
    return this.questionService.listAdmin(query);
  }

  @Post()
  @ApiOperation({ summary: '手动新建单题' })
  create(@Body() dto: CreateQuestionDto) {
    return this.questionService.create(dto);
  }

  @Post('batch-publish')
  @ApiOperation({ summary: '批量发布题目' })
  batchPublish(@Body() dto: BatchPublishDto) {
    return this.questionService.batchPublish(dto);
  }

  @Post('batch-delete')
  @ApiOperation({ summary: '批量删除题目' })
  batchDelete(@Body() dto: BatchDeleteQuestionDto) {
    return this.questionService.batchDelete(dto);
  }

  @Get('review-stats/:bankId')
  @ApiOperation({ summary: '题目审核统计' })
  getReviewStats(@Param('bankId') bankId: string) {
    return this.questionService.getReviewStats(bankId);
  }

  @Get(':id')
  @ApiOperation({ summary: '管理端题目详情' })
  detail(@Param('id') id: string) {
    return this.questionService.detailAdmin(id);
  }

  @Post(':id/readability-review')
  @ApiOperation({ summary: 'AI 预审题目可读性' })
  reviewReadability(@Param('id') id: string) {
    return this.questionService.reviewReadability(id);
  }

  @Put(':id')
  @ApiOperation({ summary: '修改题目' })
  update(@Param('id') id: string, @Body() dto: UpdateQuestionDto) {
    return this.questionService.update(id, dto);
  }

  @Delete(':id')
  @ApiOperation({ summary: '删除题目' })
  remove(@Param('id') id: string) {
    return this.questionService.remove(id);
  }
}
