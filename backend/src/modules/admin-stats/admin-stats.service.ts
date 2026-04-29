import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { QuestionBank } from '../bank/entities/question-bank.entity';
import { Question, QuestionStatus } from '../question/entities/question.entity';
import { UserRecord } from '../record/entities/user-record.entity';
import { User } from '../user/entities/user.entity';

@Injectable()
export class AdminStatsService {
  constructor(
    @InjectRepository(User)
    private readonly userRepository: Repository<User>,
    @InjectRepository(QuestionBank)
    private readonly bankRepository: Repository<QuestionBank>,
    @InjectRepository(Question)
    private readonly questionRepository: Repository<Question>,
    @InjectRepository(UserRecord)
    private readonly recordRepository: Repository<UserRecord>,
  ) {}

  async overview() {
    const today = this.startOfToday();
    const week = this.startOfWeek();
    const [
      totalUsers,
      activeUsersToday,
      activeUsersWeek,
      newUsersToday,
      newUsersWeek,
      totalBanks,
      publishedBanks,
      totalQuestions,
      publishedQuestions,
      answeredToday,
      answeredWeek,
      answeredAll,
      correctAll,
    ] = await Promise.all([
      this.userRepository.count(),
      this.distinctUsersSince(today),
      this.distinctUsersSince(week),
      this.countUsersSince(today),
      this.countUsersSince(week),
      this.bankRepository.count(),
      this.bankRepository.count({ where: { status: 'published' as any } }),
      this.questionRepository.count(),
      this.questionRepository.count({ where: { status: QuestionStatus.Published } }),
      this.countRecordsSince(today),
      this.countRecordsSince(week),
      this.recordRepository.count(),
      this.recordRepository.count({ where: { is_correct: true } }),
    ]);
    return {
      total_users: totalUsers,
      active_users_today: activeUsersToday,
      active_users_week: activeUsersWeek,
      new_users_today: newUsersToday,
      new_users_week: newUsersWeek,
      total_banks: totalBanks,
      published_banks: publishedBanks,
      total_questions: totalQuestions,
      published_questions: publishedQuestions,
      total_answered_today: answeredToday,
      total_answered_week: answeredWeek,
      total_answered_all: answeredAll,
      avg_accuracy_rate: answeredAll ? Number(((correctAll / answeredAll) * 100).toFixed(1)) : 0,
    };
  }

  async trend() {
    const since = new Date();
    since.setDate(since.getDate() - 30);
    const rows = await this.recordRepository
      .createQueryBuilder('record')
      .select('DATE(record.created_at)', 'date')
      .addSelect('COUNT(*)', 'answer_count')
      .addSelect('COUNT(DISTINCT record.user_id)', 'user_count')
      .addSelect('SUM(CASE WHEN record.is_correct = true THEN 1 ELSE 0 END)', 'correct')
      .where('record.created_at >= :since', { since })
      .groupBy('DATE(record.created_at)')
      .orderBy('DATE(record.created_at)', 'ASC')
      .getRawMany();
    return rows.map((row) => {
      const answerCount = Number(row.answer_count);
      const correct = Number(row.correct || 0);
      return {
        date: this.formatDate(row.date),
        answer_count: answerCount,
        user_count: Number(row.user_count),
        accuracy_rate: answerCount ? Number(((correct / answerCount) * 100).toFixed(1)) : 0,
      };
    });
  }

  async hotQuestions(query: { bank_id?: string; sort_by?: string; limit?: number }) {
    const limit = Math.min(Number(query.limit || 20), 100);
    const qb = this.questionRepository
      .createQueryBuilder('question')
      .leftJoinAndSelect('question.bank', 'bank')
      .take(limit);
    if (query.bank_id) qb.andWhere('question.bank_id = :bankId', { bankId: query.bank_id });
    const sortBy = query.sort_by === 'correct_rate'
      ? 'question.correct_rate'
      : query.sort_by === 'wrong_rate'
        ? 'question.correct_rate'
        : 'question.answer_count';
    qb.orderBy(sortBy, query.sort_by === 'wrong_rate' ? 'ASC' : 'DESC');
    const questions = await qb.getMany();
    return questions.map((question) => ({
      id: question.id,
      index_num: question.index_num,
      content: question.content.slice(0, 60),
      type: question.type,
      answer_count: question.answer_count,
      correct_rate: question.correct_rate,
      bank: question.bank ? { id: question.bank.id, name: question.bank.name } : null,
    }));
  }

  async activeUsers(query: { period?: string; page?: number; pageSize?: number }) {
    const page = Number(query.page || 1);
    const pageSize = Number(query.pageSize || 20);
    const since = this.periodStart(query.period || 'week');
    const qb = this.recordRepository
      .createQueryBuilder('record')
      .leftJoin('record.user', 'user')
      .select('record.user_id', 'user_id')
      .addSelect('user.nickname', 'nickname')
      .addSelect('user.phone', 'phone')
      .addSelect('COUNT(*)', 'answered_count')
      .addSelect('SUM(CASE WHEN record.is_correct = true THEN 1 ELSE 0 END)', 'correct')
      .addSelect('MAX(record.created_at)', 'last_active_at')
      .where('record.created_at >= :since', { since })
      .groupBy('record.user_id')
      .addGroupBy('user.nickname')
      .addGroupBy('user.phone')
      .orderBy('COUNT(*)', 'DESC')
      .offset((page - 1) * pageSize)
      .limit(pageSize);
    const rows = await qb.getRawMany();
    return {
      list: rows.map((row) => {
        const answered = Number(row.answered_count);
        const correct = Number(row.correct || 0);
        return {
          user_id: row.user_id,
          nickname: row.nickname,
          phone: row.phone,
          answered_count: answered,
          accuracy_rate: answered ? Number(((correct / answered) * 100).toFixed(1)) : 0,
          last_active_at: row.last_active_at,
        };
      }),
      total: rows.length,
      page,
      pageSize,
    };
  }

  async banks() {
    const rows = await this.bankRepository
      .createQueryBuilder('bank')
      .leftJoin('bank.questions', 'question')
      .leftJoin('question.records', 'record')
      .select('bank.id', 'id')
      .addSelect('bank.name', 'name')
      .addSelect('bank.subject', 'subject')
      .addSelect('bank.source', 'source')
      .addSelect('bank.total_count', 'total_count')
      .addSelect('COUNT(record.id)', 'answer_count')
      .addSelect('COUNT(DISTINCT record.user_id)', 'user_count')
      .addSelect('SUM(CASE WHEN record.is_correct = true THEN 1 ELSE 0 END)', 'correct')
      .groupBy('bank.id')
      .orderBy('COUNT(record.id)', 'DESC')
      .getRawMany();
    return rows.map((row) => {
      const answerCount = Number(row.answer_count);
      const correct = Number(row.correct || 0);
      return {
        id: row.id,
        name: row.name,
        subject: row.subject,
        source: row.source,
        total_count: Number(row.total_count),
        answer_count: answerCount,
        user_count: Number(row.user_count),
        avg_accuracy_rate: answerCount ? Number(((correct / answerCount) * 100).toFixed(1)) : 0,
      };
    });
  }

  private distinctUsersSince(since: Date) {
    return this.recordRepository
      .createQueryBuilder('record')
      .select('COUNT(DISTINCT record.user_id)', 'count')
      .where('record.created_at >= :since', { since })
      .getRawOne()
      .then((row) => Number(row.count));
  }

  private countUsersSince(since: Date) {
    return this.userRepository
      .createQueryBuilder('user')
      .where('user.created_at >= :since', { since })
      .getCount();
  }

  private countRecordsSince(since: Date) {
    return this.recordRepository
      .createQueryBuilder('record')
      .where('record.created_at >= :since', { since })
      .getCount();
  }

  private startOfToday() {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    return date;
  }

  private startOfWeek() {
    const date = this.startOfToday();
    const day = date.getDay() || 7;
    date.setDate(date.getDate() - day + 1);
    return date;
  }

  private periodStart(period: string) {
    const date = this.startOfToday();
    if (period === 'today') return date;
    date.setDate(date.getDate() - (period === 'month' ? 30 : 7));
    return date;
  }

  private formatDate(value: string | Date) {
    const date = value instanceof Date ? value : new Date(value);
    return date.toISOString().slice(0, 10);
  }
}
