import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Material } from '../question/entities/material.entity';
import { Question } from '../question/entities/question.entity';
import { MaterialController } from './material.controller';
import { MaterialService } from './material.service';

@Module({
  imports: [JwtModule.register({}), TypeOrmModule.forFeature([Material, Question])],
  controllers: [MaterialController],
  providers: [MaterialService],
})
export class MaterialModule {}
