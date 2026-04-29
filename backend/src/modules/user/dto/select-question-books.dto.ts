import { ApiProperty } from '@nestjs/swagger';
import { ArrayUnique, IsArray, IsUUID } from 'class-validator';

export class SelectQuestionBooksDto {
  @ApiProperty({
    example: [
      '6ed4a8a5-75f4-45f6-b9b5-4d1d4a2a7f01',
      '58d36e47-9825-4f87-9da4-71a36f94c8de',
    ],
  })
  @IsArray()
  @ArrayUnique()
  @IsUUID('4', { each: true })
  bankIds: string[];
}
