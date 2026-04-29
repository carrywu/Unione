import { Body, Controller, Delete, Get, Param, Post, Query, Res, UseGuards } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { Response } from 'express';
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

  @Delete('task/:taskId')
  @ApiOperation({ summary: '删除解析任务记录' })
  remove(@Param('taskId') taskId: string) {
    return this.pdfService.remove(taskId);
  }
}
