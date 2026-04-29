import http from './http';

export type AnswerBookMode = 'text' | 'image' | 'auto';
export type AnswerSourceStatus = 'unmatched' | 'matched' | 'ambiguous' | 'conflict' | 'ignored';

export interface AnswerSource {
  id: string;
  bank_id: string;
  parse_task_id: string;
  source_pdf_url: string;
  source_page_num: number;
  source_page_range?: number[];
  source_bbox?: number[];
  section_key?: string;
  question_index: number;
  question_anchor?: string;
  answer?: string;
  analysis_text?: string;
  analysis_image_url?: string;
  raw_text?: string;
  confidence: number;
  parse_mode: 'text' | 'image';
  status: AnswerSourceStatus;
  matched_question_id?: string;
  match_score?: number;
  matched_question?: {
    id: string;
    index_num: number;
    content: string;
    answer?: string;
    analysis?: string;
    analysis_image_url?: string;
  };
  created_at: string;
}

export function createAnswerBookTask(
  bankId: string,
  payload: {
    file_url: string;
    file_name?: string;
    mode: AnswerBookMode;
  },
) {
  return http.post<{ task_id: string }, { task_id: string }>(
    `/admin/banks/${bankId}/answer-books`,
    payload,
  );
}

export function matchAnswerBookTask(taskId: string) {
  return http.post<
    { total: number; matched: number; ambiguous: number; unmatched: number; ignored?: number },
    { total: number; matched: number; ambiguous: number; unmatched: number; ignored?: number }
  >(`/admin/answer-books/${taskId}/match`);
}

export function getAnswerSources(params?: {
  bank_id?: string;
  parse_task_id?: string;
  status?: AnswerSourceStatus | '';
}) {
  return http.get<AnswerSource[], AnswerSource[]>('/admin/answer-sources', { params });
}

export function bindAnswerSource(sourceId: string, questionId: string) {
  return http.post(`/admin/answer-sources/${sourceId}/bind`, {
    question_id: questionId,
  });
}

export function unbindAnswerSource(sourceId: string) {
  return http.post(`/admin/answer-sources/${sourceId}/unbind`);
}
