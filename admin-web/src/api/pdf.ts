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

export interface AiPreauditDebug {
  taskId: string;
  bankId: string;
  status: string;
  debug_dir?: string;
  qwen_vl_enabled: boolean;
  qwen_vl_call_count: number;
  final_verdict?: Record<string, unknown> | null;
  final_preview_payload?: {
    questions?: Array<Record<string, any>>;
  } | null;
  ai_audit_results?: Array<Record<string, any>>;
  page_understanding?: Array<Record<string, any>>;
  semantic_groups?: Array<Record<string, any>>;
  recrop_plan?: Array<Record<string, any>>;
  artifact_refs?: Record<string, string>;
}

export interface PaperCandidate {
  candidate_id: string;
  question_no?: number | string | null;
  stem?: string | null;
  options: Record<'A' | 'B' | 'C' | 'D', string>;
  answer_suggestion?: string | null;
  answer_confidence?: number | null;
  answer_unknown_reason?: string | null;
  analysis_suggestion?: string | null;
  analysis_confidence?: number | null;
  analysis_unknown_reason?: string | null;
  visual_assets?: Array<Record<string, any>>;
  preview_image_path?: string | null;
  source_page_refs?: Array<number | string>;
  source_bbox?: number[] | null;
  source_text_span?: string | null;
  visual_parse_status?: string;
  ai_audit_status?: string;
  ai_audit_verdict?: string | null;
  ai_audit_summary?: string | null;
  risk_flags?: string[];
  need_manual_fix: boolean;
  can_add_to_paper: boolean;
  cannot_add_reason?: string | null;
  manual_review_status?: string | null;
  manualReviewable?: boolean;
  manualForceAddAllowed?: boolean;
  missingContextReason?: string | null;
  recommendedAction?: string | null;
  source_locator_available?: boolean;
  source_artifacts_refs?: Record<string, string>;
}

export interface PaperCandidatesResponse {
  taskId: string;
  bankId: string;
  status: string;
  debug_dir?: string;
  provider?: string | null;
  model?: string | null;
  summary: {
    total: number;
    can_add_count: number;
    need_manual_fix_count: number;
    ai_passed_count: number;
    ai_warning_count: number;
    ai_failed_count: number;
  };
  questions: PaperCandidate[];
  artifact_refs?: Record<string, string>;
}

export interface DraftPaper {
  paper_id: string;
  title: string;
  sections: Array<{ id: string; title: string; order: number }>;
  questions: Array<Record<string, any>>;
  score: number;
  order: number;
  source_task_id: string;
  source_bank_id: string;
  debug_dir?: string;
  created_at: string;
  updated_at?: string;
  preview?: Record<string, any>;
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

export function getAiPreauditDebug(taskId: string) {
  return http.get<AiPreauditDebug, AiPreauditDebug>(`/admin/pdf/task/${taskId}/ai-preaudit-debug`);
}

export function getPaperCandidates(taskId: string) {
  return http.get<PaperCandidatesResponse, PaperCandidatesResponse>(`/admin/pdf/task/${taskId}/paper-candidates`);
}

export function createDraftPaper(payload: Record<string, unknown>) {
  return http.post<DraftPaper, DraftPaper>('/admin/pdf/papers/draft', payload);
}

export function getDraftPaper(paperId: string) {
  return http.get<DraftPaper, DraftPaper>(`/admin/pdf/papers/${paperId}`);
}

export function updateDraftPaper(paperId: string, payload: Record<string, unknown>) {
  return http.put<DraftPaper, DraftPaper>(`/admin/pdf/papers/${paperId}`, payload);
}

export function getDraftPaperPreview(paperId: string) {
  return http.get<DraftPaper, DraftPaper>(`/admin/pdf/papers/${paperId}/preview`);
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
