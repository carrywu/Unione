import {
  Column,
  CreateDateColumn,
  Entity,
  Index,
  JoinColumn,
  ManyToOne,
  PrimaryGeneratedColumn,
} from 'typeorm';
import { QuestionBank } from '../../bank/entities/question-bank.entity';

export enum ParseTaskStatus {
  Pending = 'pending',
  Processing = 'processing',
  Done = 'done',
  Failed = 'failed',
  Paused = 'paused',
}

export enum ParseTaskType {
  QuestionBook = 'question_book',
  AnswerBook = 'answer_book',
}

export enum AnswerBookMode {
  Text = 'text',
  Image = 'image',
  Auto = 'auto',
}

@Index(['bank_id', 'status'])
@Index(['status', 'created_at'])
@Index(['task_type'])
@Entity('parse_tasks')
export class ParseTask {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ name: 'bank_id' })
  bank_id: string;

  @Column({ name: 'file_url' })
  file_url: string;

  @Column({ name: 'file_name', default: '' })
  file_name: string;

  @Column({
    name: 'task_type',
    type: 'enum',
    enum: ParseTaskType,
    default: ParseTaskType.QuestionBook,
  })
  task_type: ParseTaskType;

  @Column({
    name: 'answer_book_mode',
    type: 'enum',
    enum: AnswerBookMode,
    nullable: true,
  })
  answer_book_mode?: AnswerBookMode;

  @Column({
    type: 'enum',
    enum: ParseTaskStatus,
    default: ParseTaskStatus.Pending,
  })
  status: ParseTaskStatus;

  @Column({ type: 'int', default: 0 })
  progress: number;

  @Column({ name: 'total_count', type: 'int', default: 0 })
  total_count: number;

  @Column({ name: 'done_count', type: 'int', default: 0 })
  done_count: number;

  @Column({ type: 'int', default: 0 })
  attempt: number;

  @Column({ type: 'text', nullable: true })
  result_summary?: string;

  @Column({ type: 'text', nullable: true })
  error?: string;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @ManyToOne(() => QuestionBank, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'bank_id' })
  bank: QuestionBank;
}
