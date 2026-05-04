import http from './http';

export interface ParseTask {
  id?: string;
  bank_id?: string;
  file_url?: string;
  file_name?: string;
  task_type?: 'question_book' | 'answer_book';
  answer_book_mode?: 'text' | 'image' | 'auto';
  status: 'pending' | 'processing' | 'done' | 'failed' | 'paused' | 'canceled';
  progress: number;
  total_count: number;
  done_count: number;
  result_summary?: string;
  error?: string;
  attempt?: number;
  created_at?: string;
  bank?: { id: string; name: string; subject: string };
  page_progress?: {
    total_pages: number;
    pending_pages: number;
    processing_pages: number;
    success_pages: number;
    failed_pages: number;
    retryable_pages: number;
    manifest_updated_at?: string | null;
    pages: Array<{
      page_no: number;
      status: 'pending' | 'processing' | 'success' | 'failed' | 'retryable';
      stage?: string | null;
      provider?: string | null;
      attempts?: number;
      started_at?: string | null;
      finished_at?: string | null;
      updated_at?: string | null;
      last_error_type?: string | null;
      last_error_message?: string | null;
      recovered_from_cache?: boolean;
    }>;
  };
  provider_runtime?: Record<string, any>;
  stale_processing?: boolean;
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
  question_id?: string | null;
  question_no?: number | string | null;
  stem?: string | null;
  options: Record<'A' | 'B' | 'C' | 'D', string>;
  answer?: string | null;
  analysis?: string | null;
  answer_suggestion?: string | null;
  answer_confidence?: number | null;
  answer_unknown_reason?: string | null;
  analysis_suggestion?: string | null;
  analysis_confidence?: number | null;
  analysis_unknown_reason?: string | null;
  visual_assets?: Array<Record<string, any>>;
  preview_image_path?: string | null;
  visual_summary?: string | null;
  visual_confidence?: number | null;
  source_page_refs?: Array<number | string>;
  source_bbox?: number[] | null;
  source_text_span?: string | null;
  material_group_id?: string | null;
  material_group_question_indexes?: number[];
  material_group_confidence?: number | null;
  material_group_reason?: string | null;
  shared_material?: boolean;
  visual_parse_status?: string;
  ai_audit_status?: string;
  ai_audit_verdict?: string | null;
  ai_audit_summary?: string | null;
  ai_reviewed_before_human?: boolean;
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
  provider_name?: string | null;
  provider_status?: string | null;
  provider_latency_ms?: number | null;
  provider_trace_ref?: string | null;
  provider_error?: Record<string, any> | null;
  provider_fallback_used?: boolean;
  grouping_evidence?: string[];
  grouping_confidence?: number | null;
  quality_gate?: {
    extraction_complete?: boolean;
    ocr_complete?: boolean;
    visual_assets_preserved?: boolean;
    semantic_consistent?: boolean;
    reasoning_verified?: boolean;
    review_ready?: boolean;
    extracted_but_incomplete?: boolean;
    needs_human_review?: boolean;
    blocking_reasons?: string[];
    warnings?: string[];
    per_question_status?: Array<Record<string, any>>;
  } | null;
  quality_gate_question_status?: Record<string, any> | null;
  extracted_but_incomplete?: boolean;
  review_ready?: boolean;
  needs_human_review?: boolean;
  visual_understanding?: Record<string, any> | null;
  missing_fields?: string[];
  validation_warnings?: string[];
  material?: {
    id?: string;
    content?: string;
    images?: Array<Record<string, any>>;
    source_page?: number;
    source?: string;
  } | null;
  m5_answer_book?: {
    verdict?: string;
    status?: string;
    empty_state_text?: string | null;
    answer_from_answer_book?: string | null;
    analysis_from_answer_book?: string | null;
    final_answer_suggestion?: string | null;
    final_analysis_suggestion?: string | null;
    match_confidence?: number | null;
    match_method?: string | null;
    evidence?: string[];
    evidence_details?: Record<string, any> | null;
    conflict_reason?: string | null;
    needs_human_review?: boolean;
    fixture_only?: boolean;
    decision_status?: string | null;
    matched_answer_item_id?: string | null;
    unmatched_reason?: string | null;
    report_source?: string | null;
    candidates?: Array<Record<string, any>>;
  } | null;
  m5_similarity?: {
    duplicate_status?: string;
    duplicate_cluster_id?: string | null;
    canonical_question_id?: string | null;
    similarity_candidates?: Array<{
      question_id?: string | null;
      bank_id?: string | null;
      parse_task_id?: string | null;
      question_no?: number | null;
      status?: string | null;
      review_status?: string | null;
      edge_type?: string | null;
      similarity_score?: number | null;
      stem_score?: number | null;
      options_score?: number | null;
      exact_signature_match?: boolean;
      content?: string | null;
      source_text_span?: string | null;
      answer?: string | null;
      analysis?: string | null;
      source_page_refs?: number[];
      shared_material?: boolean;
      visual_summary?: string | null;
      has_visual_context?: boolean;
    }>;
    edge_type?: string | null;
    final_similarity_score?: number | null;
    decision_status?: string | null;
    empty_state_text?: string | null;
  } | null;
  final_answer_suggestion?: string | null;
  final_analysis_suggestion?: string | null;
  answer_override?: string | null;
  analysis_override?: string | null;
  approved_for_publish?: boolean;
  quarantined?: boolean;
  review_decision_status?: string | null;
  audit_events?: Array<Record<string, any>>;
}

export interface PaperCandidatesResponse {
  taskId: string;
  bankId: string;
  status: string;
  m5a_verdict?: string;
  m5b_verdict?: string;
  publish_preview?: Record<string, any> | null;
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
  review_audit_events?: Array<Record<string, any>>;
  non_blocking_warnings?: string[];
  commercial_ocr?: Record<string, any> | null;
  questions: PaperCandidate[];
  artifact_refs?: Record<string, string>;
}

export interface ReviewActionResponse {
  task_id: string;
  candidate_id: string;
  review_decision: Record<string, any>;
  audit_event: Record<string, any>;
  audit_events: Array<Record<string, any>>;
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

export function applyPaperReviewAction(taskId: string, payload: Record<string, unknown>) {
  return http.post<ReviewActionResponse, ReviewActionResponse>(
    `/admin/pdf/task/${taskId}/review-action`,
    payload,
  );
}

export function publishDraftPaperPreview(paperId: string, payload: Record<string, unknown> = {}) {
  return http.post<Record<string, any>, Record<string, any>>(
    `/admin/pdf/papers/${paperId}/publish-preview`,
    payload,
  );
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

export function cancelTask(taskId: string) {
  return http.post<{ task_id: string; status: string }, { task_id: string; status: string }>(
    `/admin/pdf/cancel/${taskId}`,
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
