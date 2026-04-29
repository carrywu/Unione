import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { TypeOrmModule } from '@nestjs/typeorm';
import { SystemConfig } from './entities/system-config.entity';
import { PdfServiceMonitorController } from './pdf-service-monitor.controller';
import { SystemController } from './system.controller';
import { SystemService } from './system.service';

@Module({
  imports: [JwtModule.register({}), TypeOrmModule.forFeature([SystemConfig])],
  controllers: [SystemController, PdfServiceMonitorController],
  providers: [SystemService],
  exports: [TypeOrmModule, SystemService],
})
export class SystemModule {}
