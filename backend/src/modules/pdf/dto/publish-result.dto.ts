import { ApiPropertyOptional } from '@nestjs/swagger';
import { Transform } from 'class-transformer';
import { IsBoolean, IsOptional, IsString } from 'class-validator';

export class PublishResultDto {
  @ApiPropertyOptional({ description: '是否同时发布题库', default: false })
  @IsOptional()
  @Transform(({ value }) => value === 'true' || value === true)
  @IsBoolean()
  publish_bank?: boolean;

  @ApiPropertyOptional({ description: '强制发布 warning 级别题目（需提供理由）', default: false })
  @IsOptional()
  @Transform(({ value }) => value === 'true' || value === true)
  @IsBoolean()
  force_publish?: boolean;

  @ApiPropertyOptional({ description: '强制发布理由（force_publish=true 时必填）' })
  @IsOptional()
  @IsString()
  force_reason?: string;
}
