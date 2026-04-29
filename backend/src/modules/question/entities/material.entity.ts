import {
  Column,
  CreateDateColumn,
  DeleteDateColumn,
  Entity,
  Index,
  JoinColumn,
  ManyToOne,
  OneToMany,
  PrimaryGeneratedColumn,
} from 'typeorm';
import { QuestionBank } from '../../bank/entities/question-bank.entity';
import { Question } from './question.entity';

@Index(['parse_task_id'])
@Entity('materials')
export class Material {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ name: 'bank_id' })
  bank_id: string;

  @Column({ name: 'parse_task_id', nullable: true })
  parse_task_id?: string;

  @Column({ type: 'text' })
  content: string;

  @Column({ type: 'json', nullable: true })
  images: unknown[];

  @Column({ name: 'page_range', type: 'json', nullable: true })
  page_range?: number[];

  @Column({ name: 'image_refs', type: 'json', nullable: true })
  image_refs?: string[];

  @Column({ name: 'raw_text', type: 'text', nullable: true })
  raw_text?: string;

  @Column({ name: 'parse_warnings', type: 'json', nullable: true })
  parse_warnings?: string[];

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @DeleteDateColumn({ name: 'deleted_at' })
  deleted_at?: Date;

  @ManyToOne(() => QuestionBank, (bank) => bank.materials, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'bank_id' })
  bank: QuestionBank;

  @OneToMany(() => Question, (question) => question.material)
  questions: Question[];
}
