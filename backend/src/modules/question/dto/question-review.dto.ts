import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import {
  IsArray,
  IsBoolean,
  IsEnum,
  IsIn,
  IsNumber,
  IsObject,
  IsOptional,
  IsString,
} from 'class-validator';

export enum QuestionImageRole {
  Material = 'material',
  QuestionVisual = 'question_visual',
  OptionImage = 'option_image',
  Unknown = 'unknown',
}

export enum QuestionImageInsertPosition {
  AboveStem = 'above_stem',
  BelowStem = 'below_stem',
  AboveOptions = 'above_options',
  BelowOptions = 'below_options',
}

export class AddQuestionImageDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  url?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  base64?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  ref?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  caption?: string;

  @ApiPropertyOptional({ enum: QuestionImageRole })
  @IsOptional()
  @IsEnum(QuestionImageRole)
  image_role?: QuestionImageRole;

  @ApiPropertyOptional({ enum: QuestionImageInsertPosition })
  @IsOptional()
  @IsEnum(QuestionImageInsertPosition)
  insert_position?: QuestionImageInsertPosition;

  @ApiPropertyOptional()
  @IsOptional()
  @IsArray()
  bbox?: number[];

  @ApiPropertyOptional()
  @IsOptional()
  @IsNumber()
  page?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  ai_desc?: string;
}

export class ReorderQuestionImagesDto {
  @ApiProperty({ type: [String] })
  @IsArray()
  image_urls: string[];
}

export class MergeQuestionImagesDto {
  @ApiProperty()
  @IsString()
  image_url: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  next_image_url?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  same_visual_group_id?: string;
}

export class MoveQuestionImageDto {
  @ApiProperty()
  @IsString()
  image_url: string;

  @ApiPropertyOptional({ enum: ['previous', 'next'] })
  @IsOptional()
  @IsIn(['previous', 'next'])
  direction?: 'previous' | 'next';

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  target_question_id?: string;
}

export class AiRepairQuestionDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsArray()
  warnings?: string[];

  @ApiPropertyOptional()
  @IsOptional()
  @IsBoolean()
  include_neighbors?: boolean;
}

export class SplitQuestionDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  split_text?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  next_question?: Record<string, unknown>;
}

export class MergeQuestionDto {
  @ApiProperty({ enum: ['previous', 'next'] })
  @IsIn(['previous', 'next'])
  direction: 'previous' | 'next';
}
