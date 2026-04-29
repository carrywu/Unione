import {
  Column,
  CreateDateColumn,
  DeleteDateColumn,
  Entity,
  OneToMany,
  PrimaryGeneratedColumn,
} from 'typeorm';
import { Material } from '../../question/entities/material.entity';
import { Question } from '../../question/entities/question.entity';

export enum BankStatus {
  Draft = 'draft',
  Published = 'published',
}

@Entity('question_banks')
export class QuestionBank {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column()
  name: string;

  @Column()
  subject: string;

  @Column({ default: '' })
  source: string;

  @Column({ type: 'int', nullable: true })
  year: number;

  @Column({ type: 'enum', enum: BankStatus, default: BankStatus.Draft })
  status: BankStatus;

  @Column({ name: 'total_count', type: 'int', default: 0 })
  total_count: number;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @DeleteDateColumn({ name: 'deleted_at' })
  deleted_at?: Date;

  @OneToMany(() => Question, (question) => question.bank)
  questions: Question[];

  @OneToMany(() => Material, (material) => material.bank)
  materials: Material[];
}
