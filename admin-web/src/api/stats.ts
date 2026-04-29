import http from './http';

export interface AdminOverview {
  total_users: number;
  active_users_today: number;
  active_users_week: number;
  new_users_today: number;
  new_users_week: number;
  total_banks: number;
  published_banks: number;
  total_questions: number;
  published_questions: number;
  total_answered_today: number;
  total_answered_week: number;
  total_answered_all: number;
  avg_accuracy_rate: number;
}

export function getAdminOverview() {
  return http.get<AdminOverview, AdminOverview>('/admin/stats/overview');
}

export function getAdminTrend() {
  return http.get<Array<Record<string, unknown>>, Array<Record<string, unknown>>>('/admin/stats/trend');
}

export function getBankUsage() {
  return http.get<Array<Record<string, unknown>>, Array<Record<string, unknown>>>('/admin/stats/banks');
}
