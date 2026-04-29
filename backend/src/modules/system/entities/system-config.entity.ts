import {
  Column,
  Entity,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';

export enum SystemConfigValueType {
  String = 'string',
  Number = 'number',
  Boolean = 'boolean',
  Json = 'json',
}

@Entity('system_configs')
export class SystemConfig {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ unique: true })
  key: string;

  @Column({ type: 'text' })
  value: string;

  @Column({ nullable: true })
  description?: string;

  @Column({
    name: 'value_type',
    type: 'enum',
    enum: SystemConfigValueType,
    default: SystemConfigValueType.String,
  })
  value_type: SystemConfigValueType;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;
}
