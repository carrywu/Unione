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
import { UserRecord } from '../../record/entities/user-record.entity';
import { Material } from './material.entity';

export enum QuestionType {
  Single = 'single',
  Judge = 'judge',
}

export enum QuestionStatus {
  Draft = 'draft',
  Published = 'published',
}

@Index(['bank_id', 'status'])
@Index(['bank_id', 'needs_review'])
@Index(['bank_id', 'type'])
@Index(['parse_task_id'])
@Index(['material_id'])
@Index(['status', 'answer_count'])
@Entity('questions')
export class Question {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ name: 'bank_id' })
  bank_id: string;

  @Column({ name: 'material_id', nullable: true })
  material_id?: string;

  @Column({ name: 'parse_task_id', nullable: true })
  parse_task_id?: string;

  @Column({ name: 'index_num', type: 'int' })
  index_num: number;

  @Column({ type: 'enum', enum: QuestionType, default: QuestionType.Single })
  type: QuestionType;

  @Column({ type: 'text' })
  content: string;

  @Column({ nullable: true })
  option_a?: string;

  @Column({ nullable: true })
  option_b?: string;

  @Column({ nullable: true })
  option_c?: string;

  @Column({ nullable: true })
  option_d?: string;

  @Column({ length: 10, nullable: true })
  answer?: string;

  @Column({ type: 'text', nullable: true })
  analysis?: string;

  @Column({ name: 'answer_source_id', nullable: true })
  answer_source_id?: string;

  @Column({ name: 'analysis_image_url', type: 'text', nullable: true })
  analysis_image_url?: string;

  @Column({ name: 'analysis_match_confidence', type: 'float', nullable: true })
  analysis_match_confidence?: number;

  @Column({ type: 'json', nullable: true })
  images: unknown[];

  @Column({ name: 'ai_image_desc', type: 'text', nullable: true })
  ai_image_desc?: string;

  @Column({ name: 'page_num', type: 'int', nullable: true })
  page_num?: number;

  @Column({ nullable: true })
  source?: string;

  @Column({ name: 'raw_text', type: 'text', nullable: true })
  raw_text?: string;

  @Column({ name: 'parse_confidence', type: 'float', nullable: true })
  parse_confidence?: number;

  @Column({ name: 'page_range', type: 'json', nullable: true })
  page_range?: number[];

  @Column({ name: 'source_page_start', type: 'int', nullable: true })
  source_page_start?: number;

  @Column({ name: 'source_page_end', type: 'int', nullable: true })
  source_page_end?: number;

  @Column({ name: 'source_bbox', type: 'json', nullable: true })
  source_bbox?: number[];

  @Column({ name: 'source_anchor_text', nullable: true })
  source_anchor_text?: string;

  @Column({ name: 'source_confidence', type: 'float', nullable: true })
  source_confidence?: number;

  @Column({ name: 'image_refs', type: 'json', nullable: true })
  image_refs?: string[];

  @Column({ name: 'parse_warnings', type: 'json', nullable: true })
  parse_warnings?: string[];

  @Column({
    type: 'enum',
    enum: QuestionStatus,
    default: QuestionStatus.Draft,
  })
  status: QuestionStatus;

  @Column({ name: 'needs_review', default: false })
  needs_review: boolean;

  @Column({ name: 'answer_count', type: 'int', default: 0 })
  answer_count: number;

  @Column({ name: 'correct_rate', type: 'float', default: 0 })
  correct_rate: number;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @DeleteDateColumn({ name: 'deleted_at' })
  deleted_at?: Date;

  @ManyToOne(() => QuestionBank, (bank) => bank.questions, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'bank_id' })
  bank: QuestionBank;

  @ManyToOne(() => Material, (material) => material.questions, {
    nullable: true,
    onDelete: 'SET NULL',
  })
  @JoinColumn({ name: 'material_id' })
  material?: Material;

  @OneToMany(() => UserRecord, (record) => record.question)
  records: UserRecord[];
}
