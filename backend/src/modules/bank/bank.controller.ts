import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Post,
  Put,
  Query,
  UseGuards,
} from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { Roles } from '../../common/decorators/roles.decorator';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { BankService } from './bank.service';
import { CreateBankDto } from './dto/create-bank.dto';
import { QueryBankDto } from './dto/query-bank.dto';
import { UpdateBankDto } from './dto/update-bank.dto';

@ApiTags('Banks')
@Controller('api/banks')
export class ApiBankController {
  constructor(private readonly bankService: BankService) {}

  @Get()
  @ApiOperation({ summary: '用户端题库列表' })
  list(@Query() query: QueryBankDto) {
    return this.bankService.listPublished(query);
  }

  @Get(':id')
  @ApiOperation({ summary: '用户端题库详情' })
  detail(@Param('id') id: string) {
    return this.bankService.detail(id);
  }
}

@ApiTags('Admin Banks')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
@Controller('admin/banks')
export class AdminBankController {
  constructor(private readonly bankService: BankService) {}

  @Get()
  @ApiOperation({ summary: '管理端题库列表' })
  list(@Query() query: QueryBankDto) {
    return this.bankService.listAdmin(query);
  }

  @Post()
  @ApiOperation({ summary: '新建题库' })
  create(@Body() dto: CreateBankDto) {
    return this.bankService.create(dto);
  }

  @Put(':id')
  @ApiOperation({ summary: '修改题库' })
  update(@Param('id') id: string, @Body() dto: UpdateBankDto) {
    return this.bankService.update(id, dto);
  }

  @Delete(':id')
  @ApiOperation({ summary: '删除题库' })
  remove(@Param('id') id: string) {
    return this.bankService.remove(id);
  }

  @Put(':id/publish')
  @ApiOperation({ summary: '发布题库' })
  publish(@Param('id') id: string) {
    return this.bankService.publish(id);
  }
}
