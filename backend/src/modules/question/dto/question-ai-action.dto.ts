import { ApiProperty } from '@nestjs/swagger';
import { IsEnum } from 'class-validator';
import { QuestionAiAction } from '../entities/question-ai-action-log.entity';

export class QuestionAiActionDto {
  @ApiProperty({ enum: QuestionAiAction })
  @IsEnum(QuestionAiAction)
  action: QuestionAiAction;
}
