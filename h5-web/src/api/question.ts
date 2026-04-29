import http from './http';
import type { PageResult } from './bank';

export interface Question {
  id: string;
  bank_id: string;
  material_id?: string;
  index_num: number;
  type: 'single' | 'judge';
  content: string;
  option_a?: string;
  option_b?: string;
  option_c?: string;
  option_d?: string;
  answer?: string;
  analysis?: string;
  analysis_image_url?: string;
  analysis_image_urls?: string[];
  images?: Array<{
    base64?: string;
    src?: string;
    url?: string;
    ai_desc?: string;
    caption?: string;
    role?: string;
    slot?: string;
  } | string>;
  material?: {
    content: string;
    images?: Question['images'];
  };
}

export function getQuestions(bankId: string, page = 1, pageSize = 100, params?: Record<string, unknown>) {
  return http.get<PageResult<Question>, PageResult<Question>>('/api/questions', {
    params: { bankId, page, pageSize, sort_by: 'index_num', sort_order: 'ASC', ...params },
  });
}

export function getAnswer(questionId: string) {
  return http.get<
    { answer: string; analysis: string; analysis_image_url?: string; record?: unknown },
    { answer: string; analysis: string; analysis_image_url?: string; record?: unknown }
  >(
    `/api/questions/${questionId}/answer`,
  );
}
