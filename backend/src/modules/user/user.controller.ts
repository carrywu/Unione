import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Put,
  Query,
  UseGuards,
} from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { Roles } from '../../common/decorators/roles.decorator';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { QueryUserDto } from './dto/query-user.dto';
import { QueryUserRecordDto } from './dto/query-user-record.dto';
import { ResetPasswordDto } from './dto/reset-password.dto';
import { SelectQuestionBooksDto } from './dto/select-question-books.dto';
import { UpdateAvatarDto } from './dto/update-avatar.dto';
import { UpdateProfileDto } from './dto/update-profile.dto';
import { UpdateUserDto } from './dto/update-user.dto';
import { UserService } from './user.service';

@ApiTags('User')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('api/user')
export class UserController {
  constructor(private readonly userService: UserService) {}

  @Get('profile')
  @ApiOperation({ summary: '获取当前用户信息' })
  @ApiResponse({ status: 200, description: '获取成功' })
  getProfile(@CurrentUser('sub') userId: string) {
    return this.userService.getProfile(userId);
  }

  @Put('profile')
  @ApiOperation({ summary: '更新当前用户信息' })
  @ApiResponse({ status: 200, description: '更新成功' })
  updateProfile(
    @CurrentUser('sub') userId: string,
    @Body() dto: UpdateProfileDto,
  ) {
    return this.userService.updateProfile(userId, dto);
  }

  @Put('avatar')
  @ApiOperation({ summary: '更新当前用户头像' })
  updateAvatar(
    @CurrentUser('sub') userId: string,
    @Body() dto: UpdateAvatarDto,
  ) {
    return this.userService.updateAvatar(userId, dto.avatar);
  }

  @Delete('account')
  @ApiOperation({ summary: '注销当前账号' })
  removeAccount(@CurrentUser('sub') userId: string) {
    return this.userService.removeAccount(userId);
  }

  @Get('question-books')
  @ApiOperation({ summary: '获取当前用户已选题本' })
  getQuestionBooks(@CurrentUser('sub') userId: string) {
    return this.userService.getQuestionBooks(userId);
  }

  @Put('question-books')
  @ApiOperation({ summary: '选择当前用户题本' })
  selectQuestionBooks(
    @CurrentUser('sub') userId: string,
    @Body() dto: SelectQuestionBooksDto,
  ) {
    return this.userService.selectQuestionBooks(userId, dto);
  }
}

@ApiTags('Admin Users')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
@Controller('admin/users')
export class AdminUserController {
  constructor(private readonly userService: UserService) {}

  @Get()
  @ApiOperation({ summary: '管理端用户列表' })
  list(@Query() query: QueryUserDto) {
    return this.userService.listAdmin(query);
  }

  @Get(':id')
  @ApiOperation({ summary: '管理端用户详情' })
  detail(@Param('id') id: string) {
    return this.userService.detailAdmin(id);
  }

  @Get(':id/records')
  @ApiOperation({ summary: '查看某用户答题记录' })
  records(@Param('id') id: string, @Query() query: QueryUserRecordDto) {
    return this.userService.userRecords(id, query);
  }

  @Get(':id/stats')
  @ApiOperation({ summary: '查看某用户学习统计' })
  stats(@Param('id') id: string) {
    return this.userService.userStats(id);
  }

  @Put(':id')
  @ApiOperation({ summary: '管理端修改用户' })
  update(@Param('id') id: string, @Body() dto: UpdateUserDto) {
    return this.userService.updateAdmin(id, dto);
  }

  @Delete(':id')
  @ApiOperation({ summary: '管理端删除用户' })
  remove(@Param('id') id: string, @CurrentUser('sub') currentUserId: string) {
    return this.userService.removeAdmin(id, currentUserId);
  }

  @Put(':id/toggle-active')
  @ApiOperation({ summary: '启用或禁用用户账号' })
  toggleActive(
    @Param('id') id: string,
    @CurrentUser('sub') currentUserId: string,
  ) {
    return this.userService.toggleActive(id, currentUserId);
  }

  @Put(':id/reset-password')
  @ApiOperation({ summary: '重置用户密码' })
  resetPassword(
    @Param('id') id: string,
    @Body() dto: ResetPasswordDto,
  ) {
    return this.userService.resetPassword(id, dto.new_password);
  }
}
