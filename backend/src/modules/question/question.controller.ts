import {
  Body,
  Controller,
  Delete,
  Get,
  Patch,
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
import {
  AddQuestionImageDto,
  AiRepairQuestionDto,
  MergeQuestionDto,
  MergeQuestionImagesDto,
  MoveQuestionImageDto,
  ReorderQuestionImagesDto,
  SplitQuestionDto,
} from './dto/question-review.dto';
import { QueryQuestionDto } from './dto/query-question.dto';
import { QuestionAiActionDto } from './dto/question-ai-action.dto';
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

  @Patch(':id')
  @ApiOperation({ summary: '修改题目' })
  patch(@Param('id') id: string, @Body() dto: UpdateQuestionDto) {
    return this.questionService.update(id, dto);
  }

  @Post(':id/images')
  @ApiOperation({ summary: '新增题目图片' })
  addImage(@Param('id') id: string, @Body() dto: AddQuestionImageDto) {
    return this.questionService.addQuestionImage(id, dto);
  }

  @Patch(':id/images/reorder')
  @ApiOperation({ summary: '题目图片排序' })
  reorderImages(
    @Param('id') id: string,
    @Body() dto: ReorderQuestionImagesDto,
  ) {
    return this.questionService.reorderQuestionImages(id, dto.image_urls);
  }

  @Post(':id/images/merge')
  @ApiOperation({ summary: '标记相邻题目图片为同一视觉组' })
  mergeImages(
    @Param('id') id: string,
    @Body() dto: MergeQuestionImagesDto,
  ) {
    return this.questionService.mergeQuestionImages(id, dto);
  }

  @Delete(':id/images/:imageKey')
  @ApiOperation({ summary: '删除题目图片' })
  deleteImage(
    @Param('id') id: string,
    @Param('imageKey') imageKey: string,
  ) {
    return this.questionService.deleteQuestionImage(id, imageKey);
  }

  @Post(':id/move-image')
  @ApiOperation({ summary: '移动题目图片到相邻题' })
  moveImage(@Param('id') id: string, @Body() dto: MoveQuestionImageDto) {
    return this.questionService.moveQuestionImage(id, dto);
  }

  @Post(':id/ai-repair')
  @ApiOperation({ summary: 'AI 修复当前题候选结果' })
  repairWithAi(@Param('id') id: string, @Body() dto: AiRepairQuestionDto) {
    return this.questionService.repairQuestionWithAi(id, dto);
  }

  @Post(':id/ai-action')
  @ApiOperation({ summary: '记录并应用 AI 建议操作' })
  applyAiAction(
    @Param('id') id: string,
    @Body() dto: QuestionAiActionDto,
    @CurrentUser('sub') operatorId?: string,
  ) {
    return this.questionService.applyAiAction(id, dto, operatorId);
  }

  @Post(':id/split')
  @ApiOperation({ summary: '拆分当前题' })
  split(@Param('id') id: string, @Body() dto: SplitQuestionDto) {
    return this.questionService.splitQuestion(id, dto);
  }

  @Post(':id/merge')
  @ApiOperation({ summary: '合并当前题到相邻题' })
  merge(@Param('id') id: string, @Body() dto: MergeQuestionDto) {
    return this.questionService.mergeQuestion(id, dto);
  }

  @Delete(':id')
  @ApiOperation({ summary: '删除题目' })
  remove(@Param('id') id: string) {
    return this.questionService.remove(id);
  }
}
