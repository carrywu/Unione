import { Body, Controller, Headers, Param, Post, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PdfService } from './pdf.service';

@Controller('internal/pdf/tasks')
export class PdfInternalController {
  constructor(
    private readonly pdfService: PdfService,
    private readonly configService: ConfigService,
  ) {}

  @Post(':taskId/materials')
  appendMaterials(
    @Param('taskId') taskId: string,
    @Body() body: { materials?: Array<Record<string, any>> },
    @Headers('x-internal-token') token?: string,
  ) {
    this.assertInternalToken(token);
    return this.pdfService.appendCallbackMaterials(taskId, body.materials || []);
  }

  @Post(':taskId/questions')
  appendQuestions(
    @Param('taskId') taskId: string,
    @Body()
    body: {
      questions?: Array<Record<string, any>>;
      batch_start?: number;
      batch_size?: number;
      total?: number;
    },
    @Headers('x-internal-token') token?: string,
  ) {
    this.assertInternalToken(token);
    return this.pdfService.appendCallbackQuestions(taskId, body.questions || [], body.total);
  }

  @Post(':taskId/finish')
  finish(
    @Param('taskId') taskId: string,
    @Body() body: Record<string, any>,
    @Headers('x-internal-token') token?: string,
  ) {
    this.assertInternalToken(token);
    return this.pdfService.finishCallbackTask(taskId, body);
  }

  private assertInternalToken(token?: string) {
    const expected = this.configService.get<string>('PDF_SERVICE_INTERNAL_TOKEN', '');
    if (expected && token !== expected) {
      throw new UnauthorizedException('invalid internal token');
    }
  }
}
