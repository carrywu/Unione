import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { CommonModule } from './common/common.module';
import { AuthModule } from './modules/auth/auth.module';
import { AdminStatsModule } from './modules/admin-stats/admin-stats.module';
import { AnswerBookModule } from './modules/answer-book/answer-book.module';
import { BankModule } from './modules/bank/bank.module';
import { MaterialModule } from './modules/material/material.module';
import { PdfModule } from './modules/pdf/pdf.module';
import { QuestionModule } from './modules/question/question.module';
import { RecordModule } from './modules/record/record.module';
import { SystemModule } from './modules/system/system.module';
import { UploadModule } from './modules/upload/upload.module';
import { UserModule } from './modules/user/user.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    TypeOrmModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (configService: ConfigService) => {
        const type = configService.get<'mysql' | 'postgres'>(
          'DB_TYPE',
          'mysql',
        );
        return {
          type,
          host: configService.get<string>('DB_HOST', 'localhost'),
          port: Number(
            configService.get<string>(
              'DB_PORT',
              type === 'postgres' ? '5432' : '3306',
            ),
          ),
          username: configService.get<string>('DB_USER', 'root'),
          password: configService.get<string>('DB_PASS', ''),
          database: configService.get<string>('DB_NAME', 'quiz_app'),
          entities: [__dirname + '/**/*.entity{.ts,.js}'],
          synchronize: true,
        };
      },
    }),
    CommonModule,
    AuthModule,
    AdminStatsModule,
    AnswerBookModule,
    UserModule,
    BankModule,
    QuestionModule,
    RecordModule,
    MaterialModule,
    PdfModule,
    SystemModule,
    UploadModule,
  ],
})
export class AppModule {}
