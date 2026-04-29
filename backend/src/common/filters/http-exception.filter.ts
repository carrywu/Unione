import {
  ArgumentsHost,
  Catch,
  ExceptionFilter,
  HttpException,
  HttpStatus,
  Logger,
} from '@nestjs/common';
import { Request, Response } from 'express';

@Catch()
export class HttpExceptionFilter implements ExceptionFilter {
  private readonly logger = new Logger(HttpExceptionFilter.name);

  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const request = ctx.getRequest<Request>();
    const response = ctx.getResponse<Response>();
    const status =
      exception instanceof HttpException
        ? exception.getStatus()
        : HttpStatus.INTERNAL_SERVER_ERROR;

    const exceptionResponse =
      exception instanceof HttpException ? exception.getResponse() : null;
    const message = this.resolveMessage(exceptionResponse, exception);
    this.logException(request, status, message, exception);

    response.status(status).json({
      code: status,
      data: null,
      message,
    });
  }

  private resolveMessage(response: unknown, exception: unknown): string {
    if (typeof response === 'string') {
      return response;
    }

    if (response && typeof response === 'object') {
      const message = (response as { message?: string | string[] }).message;
      if (Array.isArray(message)) {
        return message.join('; ');
      }
      if (message) {
        return message;
      }
    }

    if (exception instanceof Error) {
      return exception.message;
    }

    return 'Internal server error';
  }

  private logException(
    request: Request,
    status: number,
    message: string,
    exception: unknown,
  ) {
    const method = request.method;
    const url = request.originalUrl || request.url;
    const user = (request as Request & { user?: { sub?: string; role?: string } })
      .user;
    const context = [
      `${method} ${url}`,
      `status=${status}`,
      user?.sub ? `user=${user.sub}` : null,
      user?.role ? `role=${user.role}` : null,
      `message=${message}`,
    ]
      .filter(Boolean)
      .join(' ');

    if (status >= 500) {
      const stack = exception instanceof Error ? exception.stack : undefined;
      this.logger.error(context, stack);
      return;
    }

    this.logger.warn(context);
  }
}
