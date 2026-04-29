import { ApiProperty } from '@nestjs/swagger';
import { IsNotEmpty, IsOptional, IsString } from 'class-validator';

export class ParsePdfDto {
  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  bank_id: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  file_url: string;

  @ApiProperty()
  @IsOptional()
  @IsString()
  file_name?: string;
}
