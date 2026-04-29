import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { TypeOrmModule } from '@nestjs/typeorm';
import { QuestionBank } from '../bank/entities/question-bank.entity';
import { ParseTask } from '../pdf/entities/parse-task.entity';
import { Question } from '../question/entities/question.entity';
import { SystemConfig } from '../system/entities/system-config.entity';
import { UploadModule } from '../upload/upload.module';
import { AnswerBookController } from './answer-book.controller';
import { AnswerBookService } from './answer-book.service';
import { AnswerSource } from './entities/answer-source.entity';

@Module({
  imports: [
    JwtModule.register({}),
    UploadModule,
    TypeOrmModule.forFeature([AnswerSource, ParseTask, Question, QuestionBank, SystemConfig]),
  ],
  controllers: [AnswerBookController],
  providers: [AnswerBookService],
  exports: [TypeOrmModule, AnswerBookService],
})
export class AnswerBookModule {}
