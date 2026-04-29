import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import {
  ArrayMaxSize,
  ArrayMinSize,
  IsArray,
  IsEnum,
  IsNumber,
  IsOptional,
  IsString,
} from 'class-validator';

export enum OcrRegionMode {
  Stem = 'stem',
  Options = 'options',
  Material = 'material',
  Analysis = 'analysis',
  Image = 'image',
}

export class OcrRegionDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  task_id?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  file_url?: string;

  @ApiProperty()
  @IsNumber()
  page_num: number;

  @ApiProperty({ type: [Number] })
  @IsArray()
  @ArrayMinSize(4)
  @ArrayMaxSize(4)
  bbox: number[];

  @ApiProperty({ enum: OcrRegionMode })
  @IsEnum(OcrRegionMode)
  mode: OcrRegionMode;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  question_id?: string;
}
