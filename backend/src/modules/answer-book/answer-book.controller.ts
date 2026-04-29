import { Body, Controller, Get, Param, Post, Query, UseGuards } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { Roles } from '../../common/decorators/roles.decorator';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { AnswerBookService } from './answer-book.service';
import { BindAnswerSourceDto } from './dto/bind-answer-source.dto';
import { CreateAnswerBookDto } from './dto/create-answer-book.dto';
import { QueryAnswerSourceDto } from './dto/query-answer-source.dto';

@ApiTags('Admin Answer Books')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
@Controller()
export class AnswerBookController {
  constructor(private readonly answerBookService: AnswerBookService) {}

  @Post('admin/banks/:bankId/answer-books')
  @ApiOperation({ summary: '创建答案解析册解析任务' })
  create(@Param('bankId') bankId: string, @Body() dto: CreateAnswerBookDto) {
    return this.answerBookService.create(bankId, dto);
  }

  @Post('admin/answer-books/:taskId/match')
  @ApiOperation({ summary: '触发答案源重新匹配' })
  match(@Param('taskId') taskId: string) {
    return this.answerBookService.matchTask(taskId);
  }

  @Get('admin/answer-sources')
  @ApiOperation({ summary: '查询答案源列表' })
  listSources(@Query() query: QueryAnswerSourceDto) {
    return this.answerBookService.listSources(query);
  }

  @Post('admin/answer-sources/:id/bind')
  @ApiOperation({ summary: '手动绑定答案源到题目' })
  bind(@Param('id') id: string, @Body() dto: BindAnswerSourceDto) {
    return this.answerBookService.bind(id, dto);
  }

  @Post('admin/answer-sources/:id/unbind')
  @ApiOperation({ summary: '解除答案源绑定' })
  unbind(@Param('id') id: string) {
    return this.answerBookService.unbind(id);
  }
}
