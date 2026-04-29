import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { TypeOrmModule } from '@nestjs/typeorm';
import { QuestionBank } from '../bank/entities/question-bank.entity';
import { Question } from '../question/entities/question.entity';
import { UserRecord } from '../record/entities/user-record.entity';
import { User } from '../user/entities/user.entity';
import { AdminStatsController } from './admin-stats.controller';
import { AdminStatsService } from './admin-stats.service';

@Module({
  imports: [
    JwtModule.register({}),
    TypeOrmModule.forFeature([User, QuestionBank, Question, UserRecord]),
  ],
  controllers: [AdminStatsController],
  providers: [AdminStatsService],
})
export class AdminStatsModule {}
