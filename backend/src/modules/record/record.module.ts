import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Question } from '../question/entities/question.entity';
import { UserRecord } from './entities/user-record.entity';
import { RecordController, StatsController, WrongController } from './record.controller';
import { RecordService } from './record.service';

@Module({
  imports: [JwtModule.register({}), TypeOrmModule.forFeature([UserRecord, Question])],
  controllers: [RecordController, WrongController, StatsController],
  providers: [RecordService],
  exports: [TypeOrmModule, RecordService],
})
export class RecordModule {}
