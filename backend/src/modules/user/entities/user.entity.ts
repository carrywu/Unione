import {
  Column,
  CreateDateColumn,
  DeleteDateColumn,
  Entity,
  Index,
  OneToMany,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { UserRecord } from '../../record/entities/user-record.entity';
import { UserQuestionBook } from './user-question-book.entity';

export enum UserRole {
  User = 'user',
  Admin = 'admin',
}

@Index(['phone'])
@Index(['is_active', 'role'])
@Index(['created_at'])
@Entity('users')
export class User {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ unique: true })
  phone: string;

  @Column()
  password: string;

  @Column({ default: '' })
  nickname: string;

  @Column({ default: '' })
  avatar: string;

  @Column({ type: 'enum', enum: UserRole, default: UserRole.User })
  role: UserRole;

  @Column({ default: true })
  is_active: boolean;

  @Column({ name: 'last_login_at', nullable: true })
  last_login_at?: Date;

  @Column({ name: 'last_login_ip', default: '' })
  last_login_ip: string;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @DeleteDateColumn({ name: 'deleted_at' })
  deleted_at?: Date;

  @OneToMany(() => UserRecord, (record) => record.user)
  records: UserRecord[];

  @OneToMany(() => UserQuestionBook, (book) => book.user)
  question_books: UserQuestionBook[];
}
