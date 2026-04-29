import {
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  ManyToOne,
  PrimaryGeneratedColumn,
  Unique,
} from 'typeorm';
import { QuestionBank } from '../../bank/entities/question-bank.entity';
import { User } from './user.entity';

@Entity('user_question_books')
@Unique(['user_id', 'bank_id'])
export class UserQuestionBook {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ name: 'user_id' })
  user_id: string;

  @Column({ name: 'bank_id' })
  bank_id: string;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @ManyToOne(() => User, (user) => user.question_books, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'user_id' })
  user: User;

  @ManyToOne(() => QuestionBank, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'bank_id' })
  bank: QuestionBank;
}
