import { ApiProperty } from '@nestjs/swagger';
import { IsNotEmpty, IsString } from 'class-validator';

export class UpdateAvatarDto {
  @ApiProperty({ example: 'https://example.com/avatar.png' })
  @IsString()
  @IsNotEmpty()
  avatar: string;
}
