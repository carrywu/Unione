import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { TypeOrmModule } from '@nestjs/typeorm';
import { QuestionBank } from '../bank/entities/question-bank.entity';
import { Question } from '../question/entities/question.entity';
import { UserRecord } from '../record/entities/user-record.entity';
import { User } from './entities/user.entity';
import { UserQuestionBook } from './entities/user-question-book.entity';
import { AdminUserController, UserController } from './user.controller';
import { UserService } from './user.service';

@Module({
  imports: [
    JwtModule.register({}),
    TypeOrmModule.forFeature([
      User,
      QuestionBank,
      UserQuestionBook,
      UserRecord,
      Question,
    ]),
  ],
  controllers: [UserController, AdminUserController],
  providers: [UserService],
  exports: [TypeOrmModule, UserService],
})
export class UserModule {}
