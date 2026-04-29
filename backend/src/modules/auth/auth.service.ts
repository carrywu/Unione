import {
  BadRequestException,
  ConflictException,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { JwtService } from '@nestjs/jwt';
import { InjectRepository } from '@nestjs/typeorm';
import * as bcrypt from 'bcryptjs';
import { Repository } from 'typeorm';
import { RedisService } from '../../common/services/redis.service';
import { User } from '../user/entities/user.entity';
import { LoginDto } from './dto/login.dto';
import { RegisterDto } from './dto/register.dto';
import { UpdatePasswordDto } from './dto/update-password.dto';

@Injectable()
export class AuthService {
  constructor(
    @InjectRepository(User)
    private readonly userRepository: Repository<User>,
    private readonly jwtService: JwtService,
    private readonly configService: ConfigService,
    private readonly redisService: RedisService,
  ) {}

  async register(dto: RegisterDto) {
    const exists = await this.userRepository.findOne({
      where: { phone: dto.phone },
    });
    if (exists) {
      throw new ConflictException('手机号已注册');
    }

    const user = this.userRepository.create({
      phone: dto.phone,
      nickname: dto.nickname,
      password: await bcrypt.hash(dto.password, 10),
    });
    await this.userRepository.save(user);

    return this.buildLoginResult(user);
  }

  async login(dto: LoginDto, ip = '') {
    const user = await this.userRepository.findOne({
      where: { phone: dto.phone },
    });
    if (!user) {
      throw new UnauthorizedException('手机号或密码错误');
    }

    const matched = await bcrypt.compare(dto.password, user.password);
    if (!matched) {
      throw new UnauthorizedException('手机号或密码错误');
    }
    if (!user.is_active) {
      throw new UnauthorizedException('账号已被禁用，请联系管理员');
    }

    await this.userRepository.update(user.id, {
      last_login_at: new Date(),
      last_login_ip: ip,
    });

    return this.buildLoginResult(user);
  }

  async refresh(refreshToken: string) {
    const payload = await this.verifyToken(refreshToken);
    const storedToken = await this.redisService.getRefreshToken(payload.sub);
    if (!storedToken || storedToken !== refreshToken) {
      throw new UnauthorizedException('refresh token 已失效');
    }

    return {
      access_token: await this.signAccessToken(payload),
    };
  }

  async logout(refreshToken: string) {
    const payload = await this.verifyToken(refreshToken);
    await this.redisService.delRefreshToken(payload.sub);
    return true;
  }

  async updatePassword(userId: string, dto: UpdatePasswordDto) {
    if (dto.new_password !== dto.confirm_password) {
      throw new BadRequestException('两次输入的新密码不一致');
    }
    const user = await this.userRepository.findOne({ where: { id: userId } });
    if (!user) {
      throw new UnauthorizedException('未登录');
    }
    const oldMatched = await bcrypt.compare(dto.old_password, user.password);
    if (!oldMatched) {
      throw new BadRequestException('原密码错误');
    }
    const samePassword = await bcrypt.compare(dto.new_password, user.password);
    if (samePassword) {
      throw new BadRequestException('新密码不能与原密码相同');
    }
    await this.userRepository.update(user.id, {
      password: await bcrypt.hash(dto.new_password, 10),
    });
    await this.redisService.delRefreshToken(user.id);
    return null;
  }

  private async buildLoginResult(user: User) {
    const payload = this.buildPayload(user);
    const accessToken = await this.signAccessToken(payload);
    const refreshToken = await this.signRefreshToken(payload);
    await this.redisService.set(
      `refresh_token:${user.id}`,
      refreshToken,
      this.resolveExpireSeconds(
        this.configService.get<string>('JWT_REFRESH_EXPIRE', '7d'),
      ),
    );

    return {
      access_token: accessToken,
      refresh_token: refreshToken,
      user: this.sanitizeUser(user),
    };
  }

  private buildPayload(user: User) {
    return {
      sub: user.id,
      phone: user.phone,
      role: user.role,
    };
  }

  private signAccessToken(payload: Record<string, unknown>) {
    return this.jwtService.signAsync(payload, {
      secret: this.configService.get<string>('JWT_SECRET'),
      expiresIn: this.configService.get<string>('JWT_ACCESS_EXPIRE', '2h'),
    });
  }

  private signRefreshToken(payload: Record<string, unknown>) {
    return this.jwtService.signAsync(payload, {
      secret: this.configService.get<string>('JWT_SECRET'),
      expiresIn: this.configService.get<string>('JWT_REFRESH_EXPIRE', '7d'),
    });
  }

  private verifyToken(token: string) {
    return this.jwtService.verifyAsync(token, {
      secret: this.configService.get<string>('JWT_SECRET'),
    });
  }

  private sanitizeUser(user: User) {
    const { password, ...safeUser } = user;
    return safeUser;
  }

  private resolveExpireSeconds(expire: string) {
    const value = Number.parseInt(expire, 10);
    if (expire.endsWith('d')) {
      return value * 24 * 60 * 60;
    }
    if (expire.endsWith('h')) {
      return value * 60 * 60;
    }
    if (expire.endsWith('m')) {
      return value * 60;
    }
    return value;
  }
}
