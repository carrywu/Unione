import {
  BadRequestException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { In, Repository } from 'typeorm';
import { RedisService } from '../../common/services/redis.service';
import { Question } from '../question/entities/question.entity';
import { UserRecord } from '../record/entities/user-record.entity';
import {
  BankStatus,
  QuestionBank,
} from '../bank/entities/question-bank.entity';
import { QueryUserDto } from './dto/query-user.dto';
import { QueryUserRecordDto } from './dto/query-user-record.dto';
import { SelectQuestionBooksDto } from './dto/select-question-books.dto';
import { UpdateProfileDto } from './dto/update-profile.dto';
import { UpdateUserDto } from './dto/update-user.dto';
import { User } from './entities/user.entity';
import { UserQuestionBook } from './entities/user-question-book.entity';

@Injectable()
export class UserService {
  constructor(
    @InjectRepository(User)
    private readonly userRepository: Repository<User>,
    @InjectRepository(QuestionBank)
    private readonly bankRepository: Repository<QuestionBank>,
    @InjectRepository(UserQuestionBook)
    private readonly userQuestionBookRepository: Repository<UserQuestionBook>,
    @InjectRepository(UserRecord)
    private readonly recordRepository: Repository<UserRecord>,
    @InjectRepository(Question)
    private readonly questionRepository: Repository<Question>,
    private readonly redisService: RedisService,
  ) {}

  async getProfile(userId: string) {
    const user = await this.userRepository.findOne({ where: { id: userId } });
    if (!user) {
      throw new NotFoundException('用户不存在');
    }
    return this.sanitizeUser(user);
  }

  async updateProfile(userId: string, dto: UpdateProfileDto) {
    const user = await this.userRepository.findOne({ where: { id: userId } });
    if (!user) {
      throw new NotFoundException('用户不存在');
    }

    Object.assign(user, dto);
    await this.userRepository.save(user);
    return this.sanitizeUser(user);
  }

  async updateAvatar(userId: string, avatar: string) {
    const user = await this.ensureUser(userId);
    user.avatar = avatar;
    await this.userRepository.save(user);
    return { avatar: user.avatar };
  }

  async removeAccount(userId: string) {
    const user = await this.ensureUser(userId);
    if (user.role === 'admin') {
      throw new BadRequestException('管理员账号不支持注销');
    }
    await this.redisService.delRefreshToken(userId);
    await this.userRepository.softDelete({ id: userId });
    return null;
  }

  async listAdmin(query: QueryUserDto) {
    const page = query.page || 1;
    const pageSize = query.pageSize || 20;
    const qb = this.userRepository
      .createQueryBuilder('user')
      .orderBy('user.created_at', 'DESC')
      .skip((page - 1) * pageSize)
      .take(pageSize);

    if (query.role) {
      qb.andWhere('user.role = :role', { role: query.role });
    }
    if (query.keyword) {
      qb.andWhere('(user.phone LIKE :keyword OR user.nickname LIKE :keyword)', {
        keyword: `%${query.keyword}%`,
      });
    }

    const [list, total] = await qb.getManyAndCount();
    return {
      list: list.map((user) => this.sanitizeUser(user)),
      total,
      page,
      pageSize,
    };
  }

  async updateAdmin(id: string, dto: UpdateUserDto) {
    const user = await this.ensureUser(id);
    Object.assign(user, dto);
    await this.userRepository.save(user);
    return this.sanitizeUser(user);
  }

  async detailAdmin(id: string) {
    return this.sanitizeUser(await this.ensureUser(id));
  }

  async toggleActive(id: string, currentUserId: string) {
    if (id === currentUserId) {
      throw new BadRequestException('不能禁用自己');
    }
    const user = await this.ensureUser(id);
    if (user.role === 'admin') {
      throw new BadRequestException('不能禁用管理员账号');
    }
    user.is_active = !user.is_active;
    await this.userRepository.save(user);
    if (!user.is_active) {
      await this.redisService.delRefreshToken(user.id);
    }
    return {
      id: user.id,
      is_active: user.is_active,
      message: user.is_active ? '已启用' : '已禁用',
    };
  }

  async resetPassword(id: string, newPassword: string) {
    const user = await this.ensureUser(id);
    const bcrypt = await import('bcryptjs');
    user.password = await bcrypt.hash(newPassword, 10);
    await this.userRepository.save(user);
    await this.redisService.delRefreshToken(user.id);
    return null;
  }

  async userRecords(id: string, query: QueryUserRecordDto) {
    await this.ensureUser(id);
    const page = query.page || 1;
    const pageSize = query.pageSize || 20;
    const qb = this.recordRepository
      .createQueryBuilder('record')
      .leftJoinAndSelect('record.question', 'question')
      .leftJoinAndSelect('question.bank', 'bank')
      .where('record.user_id = :userId', { userId: id })
      .orderBy('record.created_at', 'DESC')
      .skip((page - 1) * pageSize)
      .take(pageSize);
    if (query.bank_id) {
      qb.andWhere('question.bank_id = :bankId', { bankId: query.bank_id });
    }
    if (typeof query.is_correct === 'boolean') {
      qb.andWhere('record.is_correct = :isCorrect', {
        isCorrect: query.is_correct,
      });
    }
    const [list, total] = await qb.getManyAndCount();
    return { list, total, page, pageSize };
  }

  async userStats(id: string) {
    await this.ensureUser(id);
    const [totalAnswered, correctCount, wrongCount, todayAnswered, streak] =
      await Promise.all([
        this.recordRepository.count({ where: { user_id: id } }),
        this.recordRepository.count({ where: { user_id: id, is_correct: true } }),
        this.recordRepository.count({
          where: { user_id: id, is_correct: false, is_mastered: false },
        }),
        this.countSince(id, this.startOfToday()),
        this.streak(id),
      ]);
    return {
      total_answered: totalAnswered,
      correct_count: correctCount,
      accuracy_rate: totalAnswered
        ? Number(((correctCount / totalAnswered) * 100).toFixed(1))
        : 0,
      wrong_count: wrongCount,
      today_answered: todayAnswered,
      streak_days: streak.streak_days,
      by_subject: await this.bySubject(id),
    };
  }

  async removeAdmin(id: string, currentUserId: string) {
    if (id === currentUserId) {
      throw new ForbiddenException('不能删除当前登录用户');
    }
    const user = await this.ensureUser(id);
    await this.userRepository.remove(user);
    return true;
  }

  async getQuestionBooks(userId: string) {
    await this.ensureUser(userId);
    const selections = await this.userQuestionBookRepository.find({
      where: { user_id: userId },
      relations: ['bank'],
      order: { created_at: 'ASC' },
    });

    return selections
      .map((selection) => selection.bank)
      .filter((bank) => bank && bank.status === BankStatus.Published);
  }

  async selectQuestionBooks(userId: string, dto: SelectQuestionBooksDto) {
    await this.ensureUser(userId);

    if (!dto.bankIds.length) {
      await this.userQuestionBookRepository.delete({ user_id: userId });
      return [];
    }

    const banks = await this.bankRepository.find({
      where: { id: In(dto.bankIds), status: BankStatus.Published },
    });
    if (banks.length !== dto.bankIds.length) {
      throw new BadRequestException('存在无效或未发布的题本');
    }

    await this.userQuestionBookRepository.delete({ user_id: userId });
    await this.userQuestionBookRepository.save(
      dto.bankIds.map((bankId) =>
        this.userQuestionBookRepository.create({
          user_id: userId,
          bank_id: bankId,
        }),
      ),
    );

    const bankMap = new Map(banks.map((bank) => [bank.id, bank]));
    return dto.bankIds.map((bankId) => bankMap.get(bankId));
  }

  private async ensureUser(userId: string) {
    const user = await this.userRepository.findOne({ where: { id: userId } });
    if (!user) {
      throw new NotFoundException('用户不存在');
    }
    return user;
  }

  private sanitizeUser(user: User) {
    const { password, ...safeUser } = user;
    return safeUser;
  }

  private async countSince(userId: string, since: Date) {
    return this.recordRepository
      .createQueryBuilder('record')
      .where('record.user_id = :userId', { userId })
      .andWhere('record.created_at >= :since', { since })
      .getCount();
  }

  private async bySubject(userId: string) {
    const rows = await this.recordRepository
      .createQueryBuilder('record')
      .leftJoin('record.question', 'question')
      .leftJoin('question.bank', 'bank')
      .select('bank.subject', 'subject')
      .addSelect('COUNT(*)', 'answered')
      .addSelect('SUM(CASE WHEN record.is_correct = true THEN 1 ELSE 0 END)', 'correct')
      .where('record.user_id = :userId', { userId })
      .groupBy('bank.subject')
      .getRawMany();
    return rows.map((row) => {
      const answered = Number(row.answered);
      const correct = Number(row.correct || 0);
      return {
        subject: row.subject || '',
        answered,
        correct,
        accuracy_rate: answered ? Number(((correct / answered) * 100).toFixed(1)) : 0,
      };
    });
  }

  private async streak(userId: string) {
    const since = new Date();
    since.setDate(since.getDate() - 180);
    const rows = await this.recordRepository
      .createQueryBuilder('record')
      .select('DATE(record.created_at)', 'date')
      .where('record.user_id = :userId', { userId })
      .andWhere('record.created_at >= :since', { since })
      .groupBy('DATE(record.created_at)')
      .orderBy('DATE(record.created_at)', 'DESC')
      .getRawMany();
    const dates = new Set(rows.map((row) => this.formatDate(row.date)));
    const today = this.formatDate(new Date());
    const yesterdayDate = new Date();
    yesterdayDate.setDate(yesterdayDate.getDate() - 1);
    const yesterday = this.formatDate(yesterdayDate);
    const start = dates.has(today) ? new Date() : dates.has(yesterday) ? yesterdayDate : null;
    if (!start) return { streak_days: 0, last_active_date: rows[0]?.date || null };
    let streakDays = 0;
    const cursor = new Date(start);
    while (dates.has(this.formatDate(cursor))) {
      streakDays += 1;
      cursor.setDate(cursor.getDate() - 1);
    }
    return { streak_days: streakDays, last_active_date: this.formatDate(start) };
  }

  private startOfToday() {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    return date;
  }

  private formatDate(value: string | Date) {
    const date = value instanceof Date ? value : new Date(value);
    return date.toISOString().slice(0, 10);
  }
}
