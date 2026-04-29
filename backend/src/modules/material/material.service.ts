import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Material } from '../question/entities/material.entity';
import { Question } from '../question/entities/question.entity';
import { QueryMaterialDto } from './dto/query-material.dto';
import { UpdateMaterialDto } from './dto/update-material.dto';

@Injectable()
export class MaterialService {
  constructor(
    @InjectRepository(Material)
    private readonly materialRepository: Repository<Material>,
    @InjectRepository(Question)
    private readonly questionRepository: Repository<Question>,
  ) {}

  async list(query: QueryMaterialDto) {
    const page = query.page || 1;
    const pageSize = query.pageSize || 20;
    const [materials, total] = await this.materialRepository.findAndCount({
      where: { bank_id: query.bank_id },
      order: { created_at: 'DESC' },
      skip: (page - 1) * pageSize,
      take: pageSize,
    });
    const materialIds = materials.map((material) => material.id);
    const countRows = materialIds.length
      ? await this.questionRepository
          .createQueryBuilder('question')
          .select('question.material_id', 'material_id')
          .addSelect('COUNT(question.id)', 'question_count')
          .where('question.material_id IN (:...materialIds)', { materialIds })
          .groupBy('question.material_id')
          .getRawMany<{ material_id: string; question_count: string }>()
      : [];
    const countByMaterialId = new Map(
      countRows.map((row) => [
        row.material_id,
        Number(row.question_count) || 0,
      ]),
    );
    return {
      list: materials.map((material) => ({
        ...material,
        content:
          material.content.length > 100
            ? `${material.content.slice(0, 100)}...`
            : material.content,
        question_count: countByMaterialId.get(material.id) || 0,
      })),
      total,
      page,
      pageSize,
    };
  }

  async detail(id: string) {
    const material = await this.materialRepository.findOne({
      where: { id },
      relations: ['questions'],
    });
    if (!material) throw new NotFoundException('材料不存在');
    return material;
  }

  async update(id: string, dto: UpdateMaterialDto) {
    const material = await this.materialRepository.findOne({ where: { id } });
    if (!material) throw new NotFoundException('材料不存在');
    Object.assign(material, dto);
    return this.materialRepository.save(material);
  }

  async remove(id: string) {
    const material = await this.materialRepository.findOne({ where: { id } });
    if (!material) throw new NotFoundException('材料不存在');
    const result = await this.questionRepository.update(
      { material_id: id },
      { material_id: null },
    );
    await this.materialRepository.softRemove(material);
    return {
      deleted: true,
      unlinked_questions: result.affected || 0,
    };
  }
}
