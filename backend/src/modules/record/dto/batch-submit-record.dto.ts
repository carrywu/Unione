import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { ArrayNotEmpty, IsArray, ValidateNested } from 'class-validator';
import { SubmitRecordDto } from './submit-record.dto';

export class BatchSubmitRecordDto {
  @ApiProperty({ type: [SubmitRecordDto] })
  @IsArray()
  @ArrayNotEmpty()
  @ValidateNested({ each: true })
  @Type(() => SubmitRecordDto)
  records: SubmitRecordDto[];
}
