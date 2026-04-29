import { ApiProperty } from '@nestjs/swagger';
import { IsNotEmpty, Matches } from 'class-validator';

export class UpdatePasswordDto {
  @ApiProperty({ example: '123456' })
  @IsNotEmpty()
  old_password: string;

  @ApiProperty({ example: 'abc123456' })
  @IsNotEmpty()
  @Matches(/^[a-zA-Z0-9!@#$%^&*]{6,20}$/, {
    message: '新密码必须是6-20位字母、数字或特殊字符',
  })
  new_password: string;

  @ApiProperty({ example: 'abc123456' })
  @IsNotEmpty()
  confirm_password: string;
}
