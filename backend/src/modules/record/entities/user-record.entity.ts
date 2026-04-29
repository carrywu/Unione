import {
  Column,
  CreateDateColumn,
  Entity,
  Index,
  JoinColumn,
  ManyToOne,
  PrimaryGeneratedColumn,
} from 'typeorm';
import { Question } from '../../question/entities/question.entity';
import { User } from '../../user/entities/user.entity';

@Index(['user_id', 'created_at'])
@Index(['user_id', 'bank_id'])
@Index(['question_id'])
@Index(['user_id', 'question_id'])
@Entity('user_records')
export class UserRecord {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ name: 'user_id' })
  user_id: string;

  @Column({ name: 'question_id' })
  question_id: string;

  @Column({ name: 'bank_id', default: '' })
  bank_id: string;

  @Column({ name: 'user_answer', length: 10 })
  user_answer: string;

  @Column({ name: 'is_correct' })
  is_correct: boolean;

  @Column({ name: 'time_spent', type: 'int', default: 0 })
  time_spent: number;

  @Column({ name: 'removed_from_wrong', default: false })
  removed_from_wrong: boolean;

  @Column({ name: 'is_mastered', default: false })
  is_mastered: boolean;

  @Column({ name: 'mastered_at', nullable: true })
  mastered_at?: Date;

  @Column({ name: 'wrong_count', type: 'int', default: 0 })
  wrong_count: number;

  @Column({ name: 'last_wrong_at', nullable: true })
  last_wrong_at?: Date;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @ManyToOne(() => User, (user) => user.records, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'user_id' })
  user: User;

  @ManyToOne(() => Question, (question) => question.records, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'question_id' })
  question: Question;
}
