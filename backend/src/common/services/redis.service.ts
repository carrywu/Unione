import { Injectable, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Redis from 'ioredis';

@Injectable()
export class RedisService implements OnModuleInit, OnModuleDestroy {
  private client: Redis;
  private readonly fallback = new Map<string, string>();
  private readonly enabled: boolean;

  constructor(private readonly configService: ConfigService) {
    this.enabled =
      this.configService.get<string>('REDIS_ENABLED', 'true') !== 'false';
  }

  onModuleInit() {
    this.client = new Redis({
      host: this.configService.get<string>('REDIS_HOST', 'localhost'),
      port: Number(this.configService.get<string>('REDIS_PORT', '6379')),
      password: this.configService.get<string>('REDIS_PASS') || undefined,
      lazyConnect: true,
      maxRetriesPerRequest: 0,
      retryStrategy: (times) => Math.min(times * 100, 3000),
    });
    this.client.on('error', () => undefined);
  }

  async onModuleDestroy() {
    await this.client?.quit().catch(() => undefined);
  }

  async get(key: string) {
    if (!this.enabled) return this.fallback.get(key) || null;
    try {
      return await this.client.get(key);
    } catch {
      return this.fallback.get(key) || null;
    }
  }

  async set(key: string, value: string, ttlSeconds?: number) {
    this.fallback.set(key, value);
    if (!this.enabled) return;
    try {
      if (ttlSeconds) await this.client.set(key, value, 'EX', ttlSeconds);
      else await this.client.set(key, value);
    } catch {
      // Fallback keeps development usable without Redis.
    }
  }

  async del(...keys: string[]) {
    keys.forEach((key) => this.fallback.delete(key));
    if (!this.enabled || !keys.length) return;
    try {
      await this.client.del(...keys);
    } catch {
      // Fallback already cleared.
    }
  }

  async exists(key: string) {
    if (this.fallback.has(key)) return true;
    if (!this.enabled) return false;
    try {
      return (await this.client.exists(key)) === 1;
    } catch {
      return false;
    }
  }

  async expire(key: string, seconds: number) {
    if (!this.enabled) return;
    try {
      await this.client.expire(key, seconds);
    } catch {
      // Ignore Redis outages in development.
    }
  }

  async ttl(key: string) {
    if (!this.enabled) return -1;
    try {
      return await this.client.ttl(key);
    } catch {
      return -1;
    }
  }

  setRefreshToken(userId: string, token: string) {
    return this.set(`refresh_token:${userId}`, token, 7 * 24 * 3600);
  }

  getRefreshToken(userId: string) {
    return this.get(`refresh_token:${userId}`);
  }

  delRefreshToken(userId: string) {
    return this.del(`refresh_token:${userId}`);
  }

  async getOrSet<T>(
    key: string,
    factory: () => Promise<T>,
    ttlSeconds: number,
  ): Promise<T> {
    const cached = await this.get(key);
    if (cached) return JSON.parse(cached) as T;
    const data = await factory();
    await this.set(key, JSON.stringify(data), ttlSeconds);
    return data;
  }

  async ping() {
    if (!this.enabled) return true;
    try {
      return (await this.client.ping()) === 'PONG';
    } catch {
      return false;
    }
  }
}
