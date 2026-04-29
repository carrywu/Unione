import { ApiProperty } from '@nestjs/swagger';
import { IsNotEmpty, IsString } from 'class-validator';

export class BindAnswerSourceDto {
  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  question_id: string;
}
