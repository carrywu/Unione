import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsArray, IsEnum, IsInt, IsNotEmpty, IsOptional, IsString } from 'class-validator';
import { QuestionStatus, QuestionType } from '../entities/question.entity';

export class CreateQuestionDto {
  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  bank_id: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  material_id?: string;

  @ApiProperty()
  @IsInt()
  index_num: number;

  @ApiProperty({ enum: QuestionType })
  @IsEnum(QuestionType)
  type: QuestionType;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  content: string;

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
  @IsArray()
  images?: string[];

  @ApiPropertyOptional({ enum: QuestionStatus })
  @IsOptional()
  @IsEnum(QuestionStatus)
  status?: QuestionStatus;
}
