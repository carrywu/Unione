import { ApiPropertyOptional } from '@nestjs/swagger';
import { IsBoolean, IsEnum, IsInt, IsOptional, IsString } from 'class-validator';
import { QuestionStatus, QuestionType } from '../entities/question.entity';

export class UpdateQuestionDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  bank_id?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  material_id?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  index_num?: number;

  @ApiPropertyOptional({ enum: QuestionType })
  @IsOptional()
  @IsEnum(QuestionType)
  type?: QuestionType;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  content?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  option_a?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  option_b?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  option_c?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  option_d?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  answer?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  analysis?: string;

  @ApiPropertyOptional()
  @IsOptional()
  images?: unknown[];

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  ai_image_desc?: string;

  @ApiPropertyOptional({ enum: QuestionStatus })
  @IsOptional()
  @IsEnum(QuestionStatus)
  status?: QuestionStatus;

  @ApiPropertyOptional()
  @IsOptional()
  @IsBoolean()
  needs_review?: boolean;
}
