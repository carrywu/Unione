import { ForbiddenException, Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { PaginationDto } from '../../common/dto/pagination.dto';
import { Question } from '../question/entities/question.entity';
import { BatchSubmitRecordDto } from './dto/batch-submit-record.dto';
import { ClearWrongDto, QueryWrongDto, WrongPracticeDto } from './dto/query-wrong.dto';
import { SubmitRecordDto } from './dto/submit-record.dto';
import { UserRecord } from './entities/user-record.entity';

@Injectable()
export class RecordService {
  constructor(
    @InjectRepository(UserRecord)
    private readonly recordRepository: Repository<UserRecord>,
    @InjectRepository(Question)
    private readonly questionRepository: Repository<Question>,
  ) {}

  async submit(userId: string, dto: SubmitRecordDto) {
    const question = await this.questionRepository.findOne({
      where: { id: dto.question_id },
    });
    if (!question) {
      throw new NotFoundException('题目不存在');
    }

    const isCorrect = this.normalizeAnswer(dto.user_answer) === this.normalizeAnswer(question.answer);
    const record = this.recordRepository.create({
      user_id: userId,
      question_id: dto.question_id,
      bank_id: question.bank_id,
      user_answer: dto.user_answer,
      is_correct: isCorrect,
      time_spent: dto.time_spent,
      removed_from_wrong: isCorrect,
      is_mastered: false,
      wrong_count: isCorrect ? 0 : 1,
      last_wrong_at: isCorrect ? null : new Date(),
    });
    await this.recordRepository.save(record);
    await this.updateQuestionStats(question.id);

    return {
      is_correct: isCorrect,
      answer: question.answer,
      analysis: question.analysis,
      analysis_image_url: question.analysis_image_url,
    };
  }

  async batchSubmit(userId: string, dto: BatchSubmitRecordDto) {
    const results = [];
    for (const record of dto.records) {
      results.push({
        question_id: record.question_id,
        ...(await this.submit(userId, record)),
      });
    }
    return results;
  }

  async history(userId: string, query: PaginationDto) {
    const page = query.page || 1;
    const pageSize = query.pageSize || 20;
    const [list, total] = await this.recordRepository.findAndCount({
      where: { user_id: userId },
      relations: ['question'],
      order: { created_at: 'DESC' },
      skip: (page - 1) * pageSize,
      take: pageSize,
    });
    return { list, total, page, pageSize };
  }

  async wrong(userId: string, query: QueryWrongDto) {
    const page = query.page || 1;
    const pageSize = query.pageSize || 20;
    const qb = this.recordRepository
      .createQueryBuilder('record')
      .leftJoinAndSelect('record.question', 'question')
      .leftJoinAndSelect('question.bank', 'bank')
      .where('record.user_id = :userId', { userId })
      .andWhere('record.is_correct = false')
      .andWhere('record.removed_from_wrong = false')
      .andWhere('record.is_mastered = false')
      .orderBy('record.created_at', 'DESC');

    const bankId = query.bankId || query.bank_id;
    if (bankId) {
      qb.andWhere('question.bank_id = :bankId', { bankId });
    }

    const records = await qb.getMany();
    const deduped = Array.from(
      new Map(records.map((record) => [record.question_id, record])).values(),
    );
    const total = deduped.length;
    const list = deduped.slice((page - 1) * pageSize, page * pageSize);
    return { list, total, page, pageSize };
  }

  async stats(userId: string) {
    const [totalAnswered, correctCount, wrongCount] = await Promise.all([
      this.recordRepository.count({ where: { user_id: userId } }),
      this.recordRepository.count({
        where: { user_id: userId, is_correct: true },
      }),
      this.recordRepository.count({
        where: {
          user_id: userId,
          is_correct: false,
          removed_from_wrong: false,
        },
      }),
    ]);

    const [todayAnswered, weekAnswered, bySubject, streak] = await Promise.all([
      this.countSince(userId, this.startOfToday()),
      this.countSince(userId, this.startOfWeek()),
      this.bySubject(userId),
      this.streak(userId),
    ]);

    return {
      total_answered: totalAnswered,
      correct_count: correctCount,
      accuracy_rate: totalAnswered ? Number((correctCount / totalAnswered).toFixed(4)) : 0,
      wrong_count: wrongCount,
      today_answered: todayAnswered,
      this_week_answered: weekAnswered,
      streak_days: streak.streak_days,
      by_subject: bySubject,
    };
  }

  async calendar(userId: string) {
    const since = new Date();
    since.setDate(since.getDate() - 90);
    const rows = await this.recordRepository
      .createQueryBuilder('record')
      .select('DATE(record.created_at)', 'date')
      .addSelect('COUNT(*)', 'count')
      .where('record.user_id = :userId', { userId })
      .andWhere('record.created_at >= :since', { since })
      .groupBy('DATE(record.created_at)')
      .orderBy('DATE(record.created_at)', 'ASC')
      .getRawMany();
    return rows.map((row) => ({
      date: this.formatDate(row.date),
      count: Number(row.count),
    }));
  }

  async streak(userId: string) {
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

  async weakness(userId: string) {
    const rows = await this.recordRepository
      .createQueryBuilder('record')
      .leftJoin('record.question', 'question')
      .leftJoin('question.bank', 'bank')
      .select('bank.id', 'bank_id')
      .addSelect('bank.name', 'bank_name')
      .addSelect('bank.subject', 'subject')
      .addSelect('COUNT(*)', 'answered')
      .addSelect('SUM(CASE WHEN record.is_correct = true THEN 1 ELSE 0 END)', 'correct')
      .where('record.user_id = :userId', { userId })
      .groupBy('bank.id')
      .addGroupBy('bank.name')
      .addGroupBy('bank.subject')
      .having('COUNT(*) >= 5')
      .getRawMany();
    const weaknessBanks = rows
      .map((row) => {
        const answered = Number(row.answered);
        const correct = Number(row.correct || 0);
        return {
          bank_id: row.bank_id,
          bank_name: row.bank_name,
          subject: row.subject,
          answered,
          accuracy_rate: answered ? Number(((correct / answered) * 100).toFixed(1)) : 0,
        };
      })
      .sort((a, b) => a.accuracy_rate - b.accuracy_rate)
      .slice(0, 5);
    return { weakness_banks: weaknessBanks };
  }

  async removeWrong(userId: string, questionId: string) {
    await this.recordRepository.update(
      {
        user_id: userId,
        question_id: questionId,
        is_correct: false,
      },
      { removed_from_wrong: true },
    );
    return true;
  }

  async masterWrong(userId: string, id: string) {
    const record = await this.getWrongRecord(userId, id);
    record.is_mastered = true;
    record.mastered_at = new Date();
    await this.recordRepository.save(record);
    return {
      id: record.id,
      is_mastered: record.is_mastered,
      mastered_at: record.mastered_at,
    };
  }

  async unmasterWrong(userId: string, id: string) {
    const record = await this.getWrongRecord(userId, id);
    record.is_mastered = false;
    record.mastered_at = null;
    await this.recordRepository.save(record);
    return { id: record.id, is_mastered: record.is_mastered };
  }

  async clearWrong(userId: string, query: ClearWrongDto) {
    const qb = this.recordRepository
      .createQueryBuilder()
      .delete()
      .from(UserRecord)
      .where('user_id = :userId', { userId })
      .andWhere('is_correct = false');
    if (query.bank_id) qb.andWhere('bank_id = :bankId', { bankId: query.bank_id });
    if (typeof query.is_mastered === 'boolean') {
      qb.andWhere('is_mastered = :isMastered', {
        isMastered: query.is_mastered,
      });
    }
    const result = await qb.execute();
    return { deleted_count: result.affected || 0 };
  }

  async wrongPractice(userId: string, query: WrongPracticeDto) {
    const count = query.count || 20;
    const qb = this.recordRepository
      .createQueryBuilder('record')
      .leftJoinAndSelect('record.question', 'question')
      .where('record.user_id = :userId', { userId })
      .andWhere('record.is_correct = false')
      .andWhere('record.removed_from_wrong = false')
      .andWhere('record.is_mastered = false')
      .orderBy('record.created_at', 'DESC');
    if (query.bank_id) qb.andWhere('record.bank_id = :bankId', { bankId: query.bank_id });

    const records = await qb.getMany();
    const deduped = Array.from(
      new Map(records.map((record) => [record.question_id, record])).values(),
    ).filter((record) => record.question);
    return this.shuffle(deduped)
      .slice(0, count)
      .map((record) => record.question);
  }

  async wrongStats(userId: string) {
    const [totalWrong, masteredCount, byBankRows] = await Promise.all([
      this.recordRepository.count({
        where: { user_id: userId, is_correct: false, is_mastered: false },
      }),
      this.recordRepository.count({
        where: { user_id: userId, is_correct: false, is_mastered: true },
      }),
      this.recordRepository
        .createQueryBuilder('record')
        .leftJoin('record.question', 'question')
        .leftJoin('question.bank', 'bank')
        .select('bank.id', 'bank_id')
        .addSelect('bank.name', 'bank_name')
        .addSelect('bank.subject', 'subject')
        .addSelect(
          'SUM(CASE WHEN record.is_mastered = false THEN 1 ELSE 0 END)',
          'wrong_count',
        )
        .addSelect(
          'SUM(CASE WHEN record.is_mastered = true THEN 1 ELSE 0 END)',
          'mastered_count',
        )
        .where('record.user_id = :userId', { userId })
        .andWhere('record.is_correct = false')
        .groupBy('bank.id')
        .addGroupBy('bank.name')
        .addGroupBy('bank.subject')
        .getRawMany(),
    ]);
    return {
      total_wrong: totalWrong,
      mastered_count: masteredCount,
      by_bank: byBankRows.map((row) => ({
        bank_id: row.bank_id,
        bank_name: row.bank_name,
        subject: row.subject,
        wrong_count: Number(row.wrong_count || 0),
        mastered_count: Number(row.mastered_count || 0),
      })),
    };
  }

  private async getWrongRecord(userId: string, id: string) {
    const record = await this.recordRepository.findOne({ where: { id } });
    if (!record) throw new NotFoundException('错题不存在');
    if (record.user_id !== userId) throw new ForbiddenException('无权操作该错题');
    return record;
  }

  private async updateQuestionStats(questionId: string) {
    const [answered, correct] = await Promise.all([
      this.recordRepository.count({ where: { question_id: questionId } }),
      this.recordRepository.count({
        where: { question_id: questionId, is_correct: true },
      }),
    ]);
    await this.questionRepository.update(questionId, {
      answer_count: answered,
      correct_rate: answered ? Number(((correct / answered) * 100).toFixed(1)) : 0,
    });
  }

  private shuffle<T>(items: T[]) {
    const result = [...items];
    for (let i = result.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [result[i], result[j]] = [result[j], result[i]];
    }
    return result;
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

  private formatDate(value: string | Date) {
    const date = value instanceof Date ? value : new Date(value);
    return date.toISOString().slice(0, 10);
  }

  private normalizeAnswer(answer?: string) {
    return (answer || '').trim().toUpperCase();
  }
}
