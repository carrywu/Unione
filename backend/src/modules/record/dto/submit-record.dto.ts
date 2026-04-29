import { ApiProperty } from '@nestjs/swagger';
import { IsInt, IsNotEmpty, IsString, Min } from 'class-validator';

export class SubmitRecordDto {
  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  question_id: string;

  @ApiProperty({ example: 'A' })
  @IsString()
  @IsNotEmpty()
  user_answer: string;

  @ApiProperty({ example: 30 })
  @IsInt()
  @Min(0)
  time_spent: number;
}
