import {
  Body,
  Controller,
  Headers,
  Post,
  Put,
  Req,
  UnauthorizedException,
  UseGuards,
} from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import { Request } from 'express';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { AuthService } from './auth.service';
import { LoginDto } from './dto/login.dto';
import { RegisterDto } from './dto/register.dto';
import { UpdatePasswordDto } from './dto/update-password.dto';

@ApiTags('Auth')
@Controller('api/auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  @Post('register')
  @ApiOperation({ summary: '注册' })
  @ApiResponse({ status: 201, description: '注册成功' })
  register(@Body() dto: RegisterDto) {
    return this.authService.register(dto);
  }

  @Post('login')
  @ApiOperation({ summary: '登录' })
  @ApiResponse({ status: 201, description: '登录成功' })
  login(@Body() dto: LoginDto, @Req() request: Request) {
    return this.authService.login(dto, this.resolveIp(request));
  }

  @Put('password')
  @ApiBearerAuth()
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: '修改当前用户密码' })
  updatePassword(
    @CurrentUser('sub') userId: string,
    @Body() dto: UpdatePasswordDto,
  ) {
    return this.authService.updatePassword(userId, dto);
  }

  @Post('refresh')
  @ApiBearerAuth()
  @ApiOperation({ summary: '刷新 access token' })
  @ApiResponse({ status: 201, description: '刷新成功' })
  refresh(@Headers('authorization') authorization?: string) {
    return this.authService.refresh(this.extractBearerToken(authorization));
  }

  @Post('logout')
  @ApiBearerAuth()
  @ApiOperation({ summary: '退出登录' })
  @ApiResponse({ status: 201, description: '退出成功' })
  logout(@Headers('authorization') authorization?: string) {
    return this.authService.logout(this.extractBearerToken(authorization));
  }

  private extractBearerToken(authorization?: string) {
    const [type, token] = authorization?.split(' ') ?? [];
    if (type !== 'Bearer' || !token) {
      throw new UnauthorizedException('未登录');
    }
    return token;
  }

  private resolveIp(request: Request) {
    const forwarded = request.headers['x-forwarded-for'];
    return Array.isArray(forwarded)
      ? forwarded[0]
      : forwarded || request.ip || '';
  }
}
