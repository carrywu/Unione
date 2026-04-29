import { BadRequestException, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as OSS from 'ali-oss';
import { createHmac } from 'crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, extname, join } from 'node:path';
import { randomUUID } from 'crypto';

@Injectable()
export class UploadService {
  private readonly logger = new Logger(UploadService.name);
  private client?: OSS;

  constructor(private readonly configService: ConfigService) {}

  async uploadFile(file: Express.Multer.File) {
    if (!file) {
      throw new BadRequestException('请选择上传文件');
    }

    const now = new Date();
    const year = now.getFullYear();
    const month = `${now.getMonth() + 1}`.padStart(2, '0');
    const ext = extname(file.originalname);
    const key = `uploads/${year}/${month}/${randomUUID()}${ext}`;

    const provider = this.configService.get<string>('UPLOAD_PROVIDER', 'oss');
    if (provider === 'local') {
      this.logger.log(`Upload file to local filename=${file.originalname} key=${key}`);
      return this.uploadToLocal(file, key);
    }
    if (provider === 'qiniu') {
      this.logger.log(`Upload file to qiniu filename=${file.originalname} key=${key}`);
      return this.uploadToQiniu(file, key);
    }

    this.logger.log(`Upload file to oss filename=${file.originalname} key=${key}`);
    const client = this.getClient();
    await client.put(key, file.buffer);

    const domain = this.configService.get<string>('OSS_DOMAIN');
    const url = domain
      ? `${domain.replace(/\/$/, '')}/${key}`
      : client.signatureUrl(key);
    return {
      url,
      filename: file.originalname,
    };
  }

  uploadBuffer(
    buffer: Buffer,
    options: {
      filename: string;
      mimetype?: string;
      prefix?: string;
    },
  ) {
    const now = new Date();
    const year = now.getFullYear();
    const month = `${now.getMonth() + 1}`.padStart(2, '0');
    const ext = extname(options.filename) || '.png';
    const key = `${options.prefix || 'uploads'}/${year}/${month}/${randomUUID()}${ext}`;
    const file = {
      buffer,
      originalname: options.filename,
      mimetype: options.mimetype || 'application/octet-stream',
    } as Express.Multer.File;

    const provider = this.configService.get<string>('UPLOAD_PROVIDER', 'oss');
    if (provider === 'local') {
      this.logger.log(`Upload buffer to local filename=${options.filename} key=${key}`);
      return this.uploadToLocal(file, key);
    }
    if (provider === 'qiniu') {
      this.logger.log(`Upload buffer to qiniu filename=${options.filename} key=${key}`);
      return this.uploadToQiniu(file, key);
    }

    return this.uploadToOssBuffer(file, key);
  }

  private async uploadToQiniu(file: Express.Multer.File, key: string) {
    const accessKey = this.configService.get<string>('QINIU_ACCESS_KEY');
    const secretKey = this.configService.get<string>('QINIU_SECRET_KEY');
    const bucket = this.configService.get<string>('QINIU_BUCKET');
    const domain = this.configService.get<string>('QINIU_DOMAIN');
    const uploadUrl = this.configService.get<string>(
      'QINIU_UPLOAD_URL',
      'https://upload.qiniup.com',
    );

    if (!accessKey || !secretKey || !bucket || !domain) {
      throw new BadRequestException('七牛云配置不完整');
    }

    const formData = new FormData();
    formData.append('token', this.createQiniuUploadToken(bucket, key));
    formData.append('key', key);
    const fileBody = file.buffer.buffer.slice(
      file.buffer.byteOffset,
      file.buffer.byteOffset + file.buffer.byteLength,
    ) as ArrayBuffer;
    formData.append(
      'file',
      new Blob([fileBody], { type: file.mimetype || 'application/octet-stream' }),
      file.originalname,
    );

    const response = await fetch(uploadUrl, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const text = await response.text();
      this.logger.error(`Qiniu upload failed status=${response.status} body=${text}`);
      throw new BadRequestException(`七牛云上传失败: ${text}`);
    }

    this.logger.log(`Qiniu upload success key=${key}`);
    const publicUrl = `${domain.replace(/\/$/, '')}/${key}`;

    return {
      url: this.resolveQiniuDownloadUrl(publicUrl),
      filename: file.originalname,
    };
  }

  private async uploadToOssBuffer(file: Express.Multer.File, key: string) {
    const client = this.getClient();
    await client.put(key, file.buffer);
    const domain = this.configService.get<string>('OSS_DOMAIN');
    const url = domain
      ? `${domain.replace(/\/$/, '')}/${key}`
      : client.signatureUrl(key);
    return {
      url,
      filename: file.originalname,
    };
  }

  private async uploadToLocal(file: Express.Multer.File, key: string) {
    const relativePath = this.toLocalRelativePath(key);
    const absolutePath = join(process.cwd(), 'uploads', relativePath);
    await mkdir(dirname(absolutePath), { recursive: true });
    await writeFile(absolutePath, file.buffer);
    return {
      url: `${this.resolveBackendBaseUrl()}/uploads/${relativePath}`,
      filename: file.originalname,
    };
  }

  private createQiniuUploadToken(bucket: string, key: string) {
    const accessKey = this.configService.get<string>('QINIU_ACCESS_KEY');
    const secretKey = this.configService.get<string>('QINIU_SECRET_KEY');
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    const policy = this.urlSafeBase64(
      JSON.stringify({
        scope: `${bucket}:${key}`,
        deadline,
      }),
    );
    const sign = createHmac('sha1', secretKey).update(policy).digest('base64');
    return `${accessKey}:${this.base64ToUrlSafe(sign)}:${policy}`;
  }

  private resolveQiniuDownloadUrl(publicUrl: string) {
    const isPrivate = this.configService.get<string>('QINIU_PRIVATE', 'true') !== 'false';
    if (!isPrivate) {
      return publicUrl;
    }

    const accessKey = this.configService.get<string>('QINIU_ACCESS_KEY');
    const secretKey = this.configService.get<string>('QINIU_SECRET_KEY');
    const expiresIn = Number(
      this.configService.get<string>('QINIU_DOWNLOAD_EXPIRE', '86400'),
    );
    const deadline = Math.floor(Date.now() / 1000) + expiresIn;
    const separator = publicUrl.includes('?') ? '&' : '?';
    const signedBaseUrl = `${publicUrl}${separator}e=${deadline}`;
    const sign = createHmac('sha1', secretKey)
      .update(signedBaseUrl)
      .digest('base64');
    const token = `${accessKey}:${this.base64ToUrlSafe(sign)}`;
    return `${signedBaseUrl}&token=${token}`;
  }

  private urlSafeBase64(value: string) {
    return Buffer.from(value)
      .toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_');
  }

  private base64ToUrlSafe(value: string) {
    return value.replace(/\+/g, '-').replace(/\//g, '_');
  }

  private toLocalRelativePath(key: string) {
    return key.replace(/^uploads\//, '');
  }

  private resolveBackendBaseUrl() {
    return this.configService
      .get<string>('BACKEND_URL', 'http://127.0.0.1:3010')
      .replace(/\/$/, '');
  }

  private getClient() {
    if (this.client) {
      return this.client;
    }

    const region = this.configService.get<string>('OSS_REGION');
    const accessKeyId = this.configService.get<string>('OSS_ACCESS_KEY_ID');
    const accessKeySecret = this.configService.get<string>(
      'OSS_ACCESS_KEY_SECRET',
    );
    const bucket = this.configService.get<string>('OSS_BUCKET');

    if (!region || !accessKeyId || !accessKeySecret || !bucket) {
      throw new BadRequestException('OSS 配置不完整');
    }

    this.client = new OSS({
      region,
      accessKeyId,
      accessKeySecret,
      bucket,
    });
    return this.client;
  }
}
