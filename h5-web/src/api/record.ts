import http from './http';

export interface SubmitPayload {
  question_id: string;
  user_answer: string;
  time_spent: number;
}

export function submitAnswer(data: SubmitPayload) {
  return http.post<
    { is_correct: boolean; answer: string; analysis: string; analysis_image_url?: string; analysis_image_urls?: string[] },
    { is_correct: boolean; answer: string; analysis: string; analysis_image_url?: string; analysis_image_urls?: string[] }
  >(
    '/api/records/submit',
    data,
  );
}

export function batchSubmit(records: SubmitPayload[]) {
  return http.post<unknown[], unknown[]>('/api/records/batch-submit', { records });
}

export function getWrong(params?: Record<string, unknown>) {
  return http.get('/api/records/wrong', { params });
}

export function getStats() {
  return http.get<{
    total_answered: number;
    correct_count: number;
    accuracy_rate: number;
    wrong_count: number;
    today_answered: number;
    this_week_answered: number;
    streak_days: number;
    by_subject?: Array<{ subject: string; answered: number; correct: number; accuracy_rate: number }>;
  }, {
    total_answered: number;
    correct_count: number;
    accuracy_rate: number;
    wrong_count: number;
    today_answered: number;
    this_week_answered: number;
    streak_days: number;
    by_subject?: Array<{ subject: string; answered: number; correct: number; accuracy_rate: number }>;
  }>('/api/stats/overview');
}

export function getCalendar() {
  return http.get<Array<{ date: string; count: number }>, Array<{ date: string; count: number }>>('/api/stats/calendar');
}

export function getWrongStats() {
  return http.get<{
    total_wrong: number;
    mastered_count: number;
    by_bank: Array<{ bank_id: string; bank_name: string; subject: string; wrong_count: number; mastered_count: number }>;
  }, {
    total_wrong: number;
    mastered_count: number;
    by_bank: Array<{ bank_id: string; bank_name: string; subject: string; wrong_count: number; mastered_count: number }>;
  }>('/api/wrong/stats');
}

export function getWeakness() {
  return http.get<{
    weakness_banks: Array<{ bank_id: string; bank_name: string; subject: string; answered: number; accuracy_rate: number }>;
  }, {
    weakness_banks: Array<{ bank_id: string; bank_name: string; subject: string; answered: number; accuracy_rate: number }>;
  }>('/api/stats/weakness');
}

export function getStreak() {
  return http.get<{ streak_days: number; last_active_date?: string }, { streak_days: number; last_active_date?: string }>(
    '/api/stats/streak',
  );
}

export function masterWrong(id: string) {
  return http.put(`/api/wrong/${id}/master`);
}

export function unmasterWrong(id: string) {
  return http.put(`/api/wrong/${id}/unmaster`);
}

export function clearWrong(params?: Record<string, unknown>) {
  return http.delete('/api/wrong/clear', { params });
}

export function getWrongPractice(params?: Record<string, unknown>) {
  return http.get<any[], any[]>('/api/wrong/practice', { params });
}
