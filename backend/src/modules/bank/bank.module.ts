import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Material } from '../question/entities/material.entity';
import { Question } from '../question/entities/question.entity';
import { ApiBankController, AdminBankController } from './bank.controller';
import { BankService } from './bank.service';
import { QuestionBank } from './entities/question-bank.entity';

@Module({
  imports: [
    JwtModule.register({}),
    TypeOrmModule.forFeature([QuestionBank, Question, Material]),
  ],
  controllers: [ApiBankController, AdminBankController],
  providers: [BankService],
  exports: [TypeOrmModule, BankService],
})
export class BankModule {}
