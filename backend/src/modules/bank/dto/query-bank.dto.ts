import { ApiPropertyOptional } from '@nestjs/swagger';
import { IsOptional, IsString } from 'class-validator';
import { PaginationDto } from '../../../common/dto/pagination.dto';

export class QueryBankDto extends PaginationDto {
  @ApiPropertyOptional({ example: '行测' })
  @IsOptional()
  @IsString()
  subject?: string;

  @ApiPropertyOptional({ example: '真题' })
  @IsOptional()
  @IsString()
  keyword?: string;
}
