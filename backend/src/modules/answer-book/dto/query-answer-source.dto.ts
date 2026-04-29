import { ApiPropertyOptional } from '@nestjs/swagger';
import { IsOptional, IsString } from 'class-validator';

export class QueryAnswerSourceDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  bank_id?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  parse_task_id?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  status?: string;
}
