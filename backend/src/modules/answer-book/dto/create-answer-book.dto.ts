import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsIn, IsNotEmpty, IsOptional, IsString } from 'class-validator';
import { AnswerBookMode } from '../../pdf/entities/parse-task.entity';

export class CreateAnswerBookDto {
  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  file_url: string;

  @ApiPropertyOptional({ enum: AnswerBookMode, default: AnswerBookMode.Auto })
  @IsOptional()
  @IsIn([AnswerBookMode.Text, AnswerBookMode.Image, AnswerBookMode.Auto])
  mode?: AnswerBookMode;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  file_name?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  related_question_task_id?: string;
}
