import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AnswerSource } from '../answer-book/entities/answer-source.entity';
import { QuestionBank } from '../bank/entities/question-bank.entity';
import { Material } from '../question/entities/material.entity';
import { Question } from '../question/entities/question.entity';
import { SystemConfig } from '../system/entities/system-config.entity';
import { UploadModule } from '../upload/upload.module';
import { ParseTask } from './entities/parse-task.entity';
import { ApiPreviewPaperController, PdfController } from './pdf.controller';
import { PdfInternalController } from './pdf-internal.controller';
import { PdfService } from './pdf.service';

@Module({
  imports: [
    JwtModule.register({}),
    UploadModule,
    TypeOrmModule.forFeature([
      ParseTask,
      Question,
      Material,
      QuestionBank,
      SystemConfig,
      AnswerSource,
    ]),
  ],
  controllers: [PdfController, ApiPreviewPaperController, PdfInternalController],
  providers: [PdfService],
  exports: [TypeOrmModule, PdfService],
})
export class PdfModule {}
