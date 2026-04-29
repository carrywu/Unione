import {
  Column,
  CreateDateColumn,
  Entity,
  Index,
  JoinColumn,
  ManyToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { QuestionBank } from '../../bank/entities/question-bank.entity';
import { ParseTask } from '../../pdf/entities/parse-task.entity';
import { Question } from '../../question/entities/question.entity';

export enum AnswerSourceParseMode {
  Text = 'text',
  Image = 'image',
}

export enum AnswerSourceStatus {
  Unmatched = 'unmatched',
  Matched = 'matched',
  Ambiguous = 'ambiguous',
  Conflict = 'conflict',
  Ignored = 'ignored',
}

@Index(['bank_id', 'question_index'])
@Index(['bank_id', 'section_key', 'question_index'])
@Index(['parse_task_id'])
@Index(['status'])
@Entity('answer_sources')
export class AnswerSource {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ name: 'bank_id' })
  bank_id: string;

  @Column({ name: 'parse_task_id' })
  parse_task_id: string;

  @Column({ name: 'source_pdf_url', type: 'text' })
  source_pdf_url: string;

  @Column({ name: 'source_page_num', type: 'int' })
  source_page_num: number;

  @Column({ name: 'source_page_range', type: 'json', nullable: true })
  source_page_range?: number[];

  @Column({ name: 'source_bbox', type: 'json', nullable: true })
  source_bbox?: number[];

  @Column({ name: 'section_key', nullable: true })
  section_key?: string;

  @Column({ name: 'question_index', type: 'int' })
  question_index: number;

  @Column({ name: 'question_anchor', nullable: true })
  question_anchor?: string;

  @Column({ length: 10, nullable: true })
  answer?: string;

  @Column({ name: 'analysis_text', type: 'text', nullable: true })
  analysis_text?: string;

  @Column({ name: 'analysis_image_url', type: 'text', nullable: true })
  analysis_image_url?: string;

  @Column({ name: 'image_width', type: 'int', nullable: true })
  image_width?: number;

  @Column({ name: 'image_height', type: 'int', nullable: true })
  image_height?: number;

  @Column({ name: 'raw_text', type: 'text', nullable: true })
  raw_text?: string;

  @Column({ type: 'float', default: 0 })
  confidence: number;

  @Column({
    name: 'parse_mode',
    type: 'enum',
    enum: AnswerSourceParseMode,
  })
  parse_mode: AnswerSourceParseMode;

  @Column({
    type: 'enum',
    enum: AnswerSourceStatus,
    default: AnswerSourceStatus.Unmatched,
  })
  status: AnswerSourceStatus;

  @Column({ name: 'matched_question_id', nullable: true })
  matched_question_id?: string;

  @Column({ name: 'match_score', type: 'float', nullable: true })
  match_score?: number;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @ManyToOne(() => QuestionBank, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'bank_id' })
  bank: QuestionBank;

  @ManyToOne(() => ParseTask, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'parse_task_id' })
  parse_task: ParseTask;

  @ManyToOne(() => Question, { nullable: true, onDelete: 'SET NULL' })
  @JoinColumn({ name: 'matched_question_id' })
  matched_question?: Question;
}
