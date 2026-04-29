import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Material } from '../question/entities/material.entity';
import { BankStatus, QuestionBank } from './entities/question-bank.entity';
import {
  Question,
  QuestionStatus,
  QuestionType,
} from '../question/entities/question.entity';
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
    @InjectRepository(Material)
    private readonly materialRepository: Repository<Material>,
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

  async exportJson(id: string) {
    const bank = await this.detail(id);
    const questions = await this.questionRepository.find({
      where: { bank_id: id, status: QuestionStatus.Published },
      relations: ['material'],
      order: { index_num: 'ASC' },
    });
    const materialIds = [
      ...new Set(
        questions
          .map((question) => question.material_id)
          .filter((value): value is string => Boolean(value)),
      ),
    ];
    const materials = materialIds.length
      ? await this.materialRepository.find({
          where: { bank_id: id },
          order: { created_at: 'ASC' },
        })
      : [];

    return {
      bank,
      materials: materials
        .filter((material) => materialIds.includes(material.id))
        .map((material) => ({
          id: material.id,
          content: material.content,
          images: material.images || [],
          page_range: material.page_range || null,
        })),
      questions: questions.map((question) => ({
        id: question.id,
        index_num: question.index_num,
        type: question.type,
        stem: question.content,
        options:
          question.type === QuestionType.Judge
            ? {
                A: question.option_a || '',
                B: question.option_b || '',
              }
            : {
                A: question.option_a || '',
                B: question.option_b || '',
                C: question.option_c || '',
                D: question.option_d || '',
              },
        answer: question.answer || '',
        analysis: question.analysis || '',
        images: question.images || [],
        material_group: question.material_id || null,
        source_page: {
          page_num: question.page_num ?? null,
          start: question.source_page_start ?? question.page_num ?? null,
          end: question.source_page_end ?? question.page_num ?? null,
        },
      })),
    };
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
