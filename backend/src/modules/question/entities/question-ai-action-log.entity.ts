import {
  Column,
  CreateDateColumn,
  Entity,
  Index,
  JoinColumn,
  ManyToOne,
  PrimaryGeneratedColumn,
} from 'typeorm';
import { Question } from './question.entity';

export enum QuestionAiAction {
  AcceptAnswer = 'accept_ai_answer',
  AcceptAnalysis = 'accept_ai_analysis',
  AcceptBoth = 'accept_ai_both',
  IgnoreSuggestion = 'ignore_ai_suggestion',
}

@Index(['question_id', 'created_at'])
@Entity('question_ai_action_log')
export class QuestionAiActionLog {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ name: 'question_id' })
  question_id: string;

  @Column({ type: 'enum', enum: QuestionAiAction })
  action: QuestionAiAction;

  @Column({ nullable: true })
  field?: string;

  @Column({ name: 'old_value', type: 'text', nullable: true })
  old_value?: string;

  @Column({ name: 'new_value', type: 'text', nullable: true })
  new_value?: string;

  @Column({ name: 'ai_candidate_answer', nullable: true })
  ai_candidate_answer?: string;

  @Column({ name: 'ai_candidate_analysis', type: 'text', nullable: true })
  ai_candidate_analysis?: string;

  @Column({ name: 'ai_solver_provider', nullable: true })
  ai_solver_provider?: string;

  @Column({ name: 'ai_solver_model', nullable: true })
  ai_solver_model?: string;

  @Column({ name: 'ai_solver_first_model', nullable: true })
  ai_solver_first_model?: string;

  @Column({ name: 'ai_solver_final_model', nullable: true })
  ai_solver_final_model?: string;

  @Column({ name: 'ai_solver_rechecked', default: false })
  ai_solver_rechecked: boolean;

  @Column({ name: 'ai_answer_confidence', type: 'float', nullable: true })
  ai_answer_confidence?: number;

  @Column({ name: 'operator_id', nullable: true })
  operator_id?: string;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @ManyToOne(() => Question, (question) => question.ai_action_logs, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'question_id' })
  question: Question;
}
