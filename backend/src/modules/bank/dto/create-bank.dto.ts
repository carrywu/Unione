import { ApiProperty } from '@nestjs/swagger';
import { IsInt, IsNotEmpty, IsOptional, IsString } from 'class-validator';

export class CreateBankDto {
  @ApiProperty({ example: '2024 行测真题' })
  @IsString()
  @IsNotEmpty()
  name: string;

  @ApiProperty({ example: '行测' })
  @IsString()
  @IsNotEmpty()
  subject: string;

  @ApiProperty({ example: '超格' })
  @IsString()
  @IsOptional()
  source?: string;

  @ApiProperty({ example: 2024 })
  @IsInt()
  year: number;
}
