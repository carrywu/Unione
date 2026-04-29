import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import {
  BankStatus,
  QuestionBank,
} from './entities/question-bank.entity';
import { Question, QuestionStatus } from '../question/entities/question.entity';
import { CreateBankDto } from './dto/create-bank.dto';
import { QueryBankDto } from './dto/query-bank.dto';
import { UpdateBankDto } from './dto/update-bank.dto';

@Injectable()
export class BankService {
  constructor(
    @InjectRepository(QuestionBank)
    private readonly bankRepository: Repository<QuestionBank>,
    @InjectRepository(Question)
    private readonly questionRepository: Repository<Question>,
  ) {}

  listPublished(query: QueryBankDto) {
    return this.list(query, BankStatus.Published);
  }

  listAdmin(query: QueryBankDto) {
    return this.list(query);
  }

  async detail(id: string) {
    const bank = await this.bankRepository.findOne({ where: { id } });
    if (!bank) {
      throw new NotFoundException('题库不存在');
    }
    return bank;
  }

  async create(dto: CreateBankDto) {
    const bank = this.bankRepository.create({
      ...dto,
      source: dto.source || '',
    });
    return this.bankRepository.save(bank);
  }

  async update(id: string, dto: UpdateBankDto) {
    const bank = await this.detail(id);
    Object.assign(bank, dto);
    return this.bankRepository.save(bank);
  }

  async remove(id: string) {
    const bank = await this.detail(id);
    await this.bankRepository.softRemove(bank);
    return true;
  }

  async publish(id: string) {
    const bank = await this.detail(id);
    const total = await this.questionRepository.count({
      where: { bank_id: id, status: QuestionStatus.Published },
    });
    bank.status = BankStatus.Published;
    bank.total_count = total;
    return this.bankRepository.save(bank);
  }

  private async list(query: QueryBankDto, status?: BankStatus) {
    const page = query.page || 1;
    const pageSize = query.pageSize || 20;
    const qb = this.bankRepository
      .createQueryBuilder('bank')
      .orderBy('bank.created_at', 'DESC')
      .skip((page - 1) * pageSize)
      .take(pageSize);

    if (status) {
      qb.andWhere('bank.status = :status', { status });
    }
    if (query.subject) {
      qb.andWhere('bank.subject = :subject', { subject: query.subject });
    }
    if (query.keyword) {
      qb.andWhere('bank.name LIKE :keyword', {
        keyword: `%${query.keyword}%`,
      });
    }

    const [list, total] = await qb.getManyAndCount();
    return { list, total, page, pageSize };
  }
}
