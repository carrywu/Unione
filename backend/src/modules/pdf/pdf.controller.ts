import { Body, Controller, Delete, Get, Param, Post, Put, Query, Res, UseGuards } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { Response } from 'express';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { Roles } from '../../common/decorators/roles.decorator';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { ParsePdfDto } from './dto/parse-pdf.dto';
import { PublishResultDto } from './dto/publish-result.dto';
import { OcrRegionDto } from './dto/ocr-region.dto';
import { QueryParseTaskDto } from './dto/query-parse-task.dto';
import { PdfService } from './pdf.service';

@ApiTags('Admin PDF')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
@Controller('admin/pdf')
export class PdfController {
  constructor(private readonly pdfService: PdfService) {}

  @Post('parse')
  @ApiOperation({ summary: '创建 PDF 解析任务' })
  parse(@Body() dto: ParsePdfDto) {
    return this.pdfService.parse(dto);
  }

  @Post('ocr-region')
  @ApiOperation({ summary: '框选区域 OCR / 截图' })
  ocrRegion(@Body() dto: OcrRegionDto) {
    return this.pdfService.ocrRegion(dto);
  }

  @Post('crop-region')
  @ApiOperation({ summary: '框选区域截图' })
  cropRegion(@Body() dto: OcrRegionDto) {
    return this.pdfService.cropRegion(dto);
  }

  @Post('header-footer-blacklist')
  @ApiOperation({ summary: '追加页眉页脚黑名单' })
  headerFooterBlacklist(@Body() body: Record<string, unknown>) {
    return this.pdfService.addHeaderFooterBlacklist(body);
  }

  @Get('task/:taskId')
  @ApiOperation({ summary: '获取解析任务状态' })
  getTask(@Param('taskId') taskId: string) {
    return this.pdfService.getTask(taskId);
  }

  @Post('task/:taskId/publish-result')
  @ApiOperation({ summary: '发布解析结果到题库/H5' })
  publishResult(
    @Param('taskId') taskId: string,
    @Body() dto: PublishResultDto,
  ) {
    return this.pdfService.publishResult(taskId, dto);
  }

  @Post('task/:taskId/debug/generate')
  @ApiOperation({ summary: '生成 PDF visual smoke 调试产物' })
  generateDebugArtifacts(
    @Param('taskId') taskId: string,
    @Body() body: Record<string, unknown>,
  ) {
    return this.pdfService.generateDebugArtifacts(taskId, body);
  }

  @Get('task/:taskId/debug')
  @ApiOperation({ summary: '获取 PDF 调试产物 metadata' })
  getDebugArtifacts(@Param('taskId') taskId: string) {
    return this.pdfService.getDebugArtifacts(taskId);
  }

  @Get('task/:taskId/debug/summary')
  @ApiOperation({ summary: '读取 PDF 调试 summary.json' })
  getDebugSummary(@Param('taskId') taskId: string) {
    return this.pdfService.getDebugSummary(taskId);
  }

  @Get('task/:taskId/debug/review-manifest')
  @ApiOperation({ summary: '读取 PDF 调试 review manifest' })
  async getDebugReviewManifest(
    @Param('taskId') taskId: string,
    @Query('format') format: string | undefined,
    @Res({ passthrough: true }) res: Response,
  ) {
    const artifact = await this.pdfService.getDebugReviewManifest(
      taskId,
      format === 'csv' ? 'csv' : 'json',
    );
    if (artifact.contentType) {
      res.setHeader('Content-Type', artifact.contentType);
    }
    return artifact.data;
  }

  @Get('task/:taskId/ai-preaudit-debug')
  @ApiOperation({ summary: '读取 PDF AI 预审核调试摘要' })
  getAiPreauditDebug(@Param('taskId') taskId: string) {
    return this.pdfService.getAiPreauditDebug(taskId);
  }

  @Get('task/:taskId/paper-candidates')
  @ApiOperation({ summary: '读取解析任务制卷候选题' })
  getPaperCandidates(@Param('taskId') taskId: string) {
    return this.pdfService.getPaperCandidates(taskId);
  }

  @Get('task/:taskId/review-state')
  @ApiOperation({ summary: '读取 M6 审核闭环状态' })
  getReviewState(@Param('taskId') taskId: string) {
    return this.pdfService.getReviewState(taskId);
  }

  @Post('task/:taskId/review-action')
  @ApiOperation({ summary: '记录 M6 人工审核动作并写入审计事件' })
  applyReviewAction(
    @Param('taskId') taskId: string,
    @Body() body: Record<string, unknown>,
    @CurrentUser('sub') operatorId?: string,
  ) {
    return this.pdfService.applyReviewAction(taskId, body, operatorId);
  }

  @Post('papers/draft')
  @ApiOperation({ summary: '创建试卷草稿' })
  createDraftPaper(@Body() body: Record<string, unknown>) {
    return this.pdfService.createDraftPaper(body);
  }

  @Get('papers/:paperId')
  @ApiOperation({ summary: '读取试卷草稿' })
  getDraftPaper(@Param('paperId') paperId: string) {
    return this.pdfService.getDraftPaper(paperId);
  }

  @Put('papers/:paperId')
  @ApiOperation({ summary: '更新试卷草稿' })
  updateDraftPaper(
    @Param('paperId') paperId: string,
    @Body() body: Record<string, unknown>,
  ) {
    return this.pdfService.updateDraftPaper(paperId, body);
  }

  @Get('papers/:paperId/preview')
  @ApiOperation({ summary: '预览试卷草稿' })
  previewDraftPaper(@Param('paperId') paperId: string) {
    return this.pdfService.previewDraftPaper(paperId);
  }

  @Post('papers/:paperId/publish-preview')
  @ApiOperation({ summary: '将试卷草稿发布为 preview-only 试卷' })
  publishDraftPaperPreview(
    @Param('paperId') paperId: string,
    @Body() body: Record<string, unknown>,
    @CurrentUser('sub') operatorId?: string,
  ) {
    return this.pdfService.publishDraftPaperPreview(paperId, body, operatorId);
  }

  @Post('task/:taskId/h5-consistency-preview')
  @ApiOperation({ summary: '基于解析任务生成 H5 一致性预览题本' })
  buildTaskConsistencyPreview(
    @Param('taskId') taskId: string,
    @Body() body: Record<string, unknown>,
    @CurrentUser('sub') operatorId?: string,
  ) {
    return this.pdfService.buildTaskConsistencyPreview(taskId, body, operatorId);
  }

  @Get('task/:taskId/debug/artifact')
  @ApiOperation({ summary: '读取 PDF 调试 overlay/crop/screenshot artifact' })
  async getDebugArtifact(
    @Param('taskId') taskId: string,
    @Query('path') path: string,
    @Res() res: Response,
  ) {
    const artifact = await this.pdfService.getDebugArtifact(taskId, path);
    res.setHeader('Content-Type', artifact.contentType);
    if (artifact.contentLength) {
      res.setHeader('Content-Length', artifact.contentLength);
    }
    res.send(artifact.data);
  }

  @Get('proxy/:taskId')
  @ApiOperation({ summary: '代理预览原始 PDF' })
  proxy(@Param('taskId') taskId: string, @Res() res: Response) {
    return this.pdfService.proxySourcePdf(taskId, res);
  }

  @Get('tasks')
  @ApiOperation({ summary: '解析任务历史' })
  listTasks(@Query() query: QueryParseTaskDto) {
    return this.pdfService.listTasks(query);
  }

  @Post('retry/:taskId')
  @ApiOperation({ summary: '重试失败解析任务' })
  retry(@Param('taskId') taskId: string) {
    return this.pdfService.retry(taskId);
  }

  @Post('pause/:taskId')
  @ApiOperation({ summary: '暂停正在解析的任务' })
  pause(@Param('taskId') taskId: string) {
    return this.pdfService.pause(taskId);
  }

  @Post('cancel/:taskId')
  @ApiOperation({ summary: '取消解析任务' })
  cancel(@Param('taskId') taskId: string) {
    return this.pdfService.cancel(taskId);
  }

  @Delete('task/:taskId')
  @ApiOperation({ summary: '删除解析任务记录' })
  remove(@Param('taskId') taskId: string) {
    return this.pdfService.remove(taskId);
  }
}

@ApiTags('Preview Papers')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('api/preview-papers')
export class ApiPreviewPaperController {
  constructor(private readonly pdfService: PdfService) {}

  @Get(':paperId')
  @ApiOperation({ summary: '读取 preview-only 试卷' })
  getPreviewPaper(@Param('paperId') paperId: string) {
    return this.pdfService.getPreviewPaperForH5(paperId);
  }

  @Post(':paperId/submit')
  @ApiOperation({ summary: '提交 preview-only 试卷答题结果' })
  submitPreviewPaper(
    @Param('paperId') paperId: string,
    @Body() body: Record<string, unknown>,
    @CurrentUser('sub') userId?: string,
  ) {
    return this.pdfService.submitPreviewPaperAnswer(paperId, body, userId);
  }
}
