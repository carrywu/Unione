import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { TypeOrmModule } from '@nestjs/typeorm';
import { QuestionBank } from '../bank/entities/question-bank.entity';
import { ParseTask } from '../pdf/entities/parse-task.entity';
import { UserRecord } from '../record/entities/user-record.entity';
import { SystemConfig } from '../system/entities/system-config.entity';
import { Material } from './entities/material.entity';
import { QuestionAiActionLog } from './entities/question-ai-action-log.entity';
import { Question } from './entities/question.entity';
import { ApiQuestionController, AdminQuestionController } from './question.controller';
import { QuestionService } from './question.service';

@Module({
  imports: [
    JwtModule.register({}),
    TypeOrmModule.forFeature([
      Question,
      QuestionAiActionLog,
      Material,
      UserRecord,
      QuestionBank,
      ParseTask,
      SystemConfig,
    ]),
  ],
  controllers: [ApiQuestionController, AdminQuestionController],
  providers: [QuestionService],
  exports: [TypeOrmModule, QuestionService],
})
export class QuestionModule {}
