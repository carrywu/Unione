import { ApiProperty } from '@nestjs/swagger';
import { IsNotEmpty, IsString } from 'class-validator';
import { PaginationDto } from '../../../common/dto/pagination.dto';

export class QueryMaterialDto extends PaginationDto {
  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  bank_id: string;
}
