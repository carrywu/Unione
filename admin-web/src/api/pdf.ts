import http from './http';

export interface ParseTask {
  id?: string;
  bank_id?: string;
  file_url?: string;
  file_name?: string;
  task_type?: 'question_book' | 'answer_book';
  answer_book_mode?: 'text' | 'image' | 'auto';
  status: 'pending' | 'processing' | 'done' | 'failed' | 'paused';
  progress: number;
  total_count: number;
  done_count: number;
  result_summary?: string;
  error?: string;
  attempt?: number;
  created_at?: string;
  bank?: { id: string; name: string; subject: string };
}

export type OcrRegionMode = 'stem' | 'options' | 'material' | 'analysis' | 'image';

export interface OcrRegionPayload {
  task_id?: string;
  file_url?: string;
  page_num: number;
  bbox: [number, number, number, number];
  mode: OcrRegionMode;
  question_id?: string;
}

export interface OcrRegionResult {
  text: string;
  options?: Partial<Record<'A' | 'B' | 'C' | 'D', string>>;
  image_url?: string;
  page_num: number;
  bbox: [number, number, number, number];
  confidence: number;
  source: 'pdf_text_layer' | 'ocr' | 'vision_model' | 'manual_crop' | string;
  warnings: string[];
}

export interface PublishParseResultPayload {
  publish_bank: boolean;
}

export interface PublishParseResultResponse {
  task_id: string;
  bank_id: string;
  published_count: number;
  review_count?: number;
  skipped_count?: number;
  bank_status: 'draft' | 'published';
  total_count: number;
}

export function parsePdf(bankId: string, fileUrl: string, fileName?: string) {
  return http.post<{ task_id: string }, { task_id: string }>('/admin/pdf/parse', {
    bank_id: bankId,
    file_url: fileUrl,
    file_name: fileName,
  });
}

export function getTaskStatus(taskId: string) {
  return http.get<ParseTask, ParseTask>(`/admin/pdf/task/${taskId}`);
}

export function ocrPdfRegion(payload: OcrRegionPayload) {
  return http.post<OcrRegionResult, OcrRegionResult>('/admin/pdf/ocr-region', payload);
}

export function addHeaderFooterBlacklist(data: { text?: string; texts?: string[] }) {
  return http.post<{ key: string; texts: string[] }, { key: string; texts: string[] }>(
    '/admin/pdf/header-footer-blacklist',
    data,
  );
}

export function getTaskList(bankId: string) {
  return http.get<ParseTask[], ParseTask[]>('/admin/pdf/tasks', {
    params: bankId ? { bankId } : {},
  });
}

export function retryTask(taskId: string) {
  return http.post<{ task_id: string; status: string }, { task_id: string; status: string }>(
    `/admin/pdf/retry/${taskId}`,
  );
}

export function pauseTask(taskId: string) {
  return http.post<{ task_id: string; status: string }, { task_id: string; status: string }>(
    `/admin/pdf/pause/${taskId}`,
  );
}

export function publishParseResult(taskId: string, payload: PublishParseResultPayload) {
  return http.post<PublishParseResultResponse, PublishParseResultResponse>(
    `/admin/pdf/task/${taskId}/publish-result`,
    payload,
  );
}

export function deleteTask(taskId: string) {
  return http.delete<null, null>(`/admin/pdf/task/${taskId}`);
}

export function pdfProxyUrl(taskId: string) {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
  return `${baseUrl}/admin/pdf/proxy/${taskId}`;
}
