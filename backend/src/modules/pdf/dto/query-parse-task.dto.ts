import { ApiPropertyOptional } from '@nestjs/swagger';
import { IsOptional, IsString } from 'class-validator';

export class QueryParseTaskDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  bankId?: string;
}
