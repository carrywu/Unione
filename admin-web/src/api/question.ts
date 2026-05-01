import http from './http';
import type { PageResult } from './bank';

export interface Question {
  id: string;
  bank_id: string;
  material_id?: string;
  parse_task_id?: string;
  index_num: number;
  type: 'single' | 'judge';
  content: string;
  option_a?: string;
  option_b?: string;
  option_c?: string;
  option_d?: string;
  answer?: string;
  analysis?: string;
  answer_source_id?: string;
  analysis_image_url?: string;
  analysis_match_confidence?: number;
  images?: Array<{
    base64?: string;
    url?: string;
    ai_desc?: string;
    ref?: string;
    caption?: string;
    page?: number;
    role?: string;
    image_role?: 'material' | 'question_visual' | 'option_image' | 'unknown' | string;
    image_order?: number;
    insert_position?: 'above_stem' | 'below_stem' | 'above_options' | 'below_options' | string;
    bbox?: number[];
    raw_bbox?: number[];
    expanded_bbox?: number[];
    absorbed_texts?: Array<{
      id?: string;
      type?: string;
      text?: string;
      bbox?: number[];
      order_index?: number;
    }>;
    source?: string;
    assignment_confidence?: number;
    same_visual_group_id?: string;
    child_visual_ids?: string[];
    visual_parse_status?: 'success' | 'partial' | 'failed' | 'skipped' | string;
    visual_summary?: string;
    visual_confidence?: number;
    visual_error?: string;
    belongs_to_question?: boolean;
    linked_question_no?: number;
    linked_question_id?: string;
    linked_by?: 'ai' | 'layout' | 'hybrid' | 'fallback' | string;
    link_reason?: string;
  } | string>;
  ai_image_desc?: string;
  status: 'draft' | 'published';
  needs_review: boolean;
  page_num?: number;
  source?: string;
  source_page_start?: number;
  source_page_end?: number;
  source_bbox?: number[];
  source_anchor_text?: string;
  source_confidence?: number;
  raw_text?: string;
  parse_confidence?: number;
  page_range?: number[];
  image_refs?: string[];
  visual_refs?: Array<Record<string, unknown>>;
  parse_warnings?: string[];
  ai_corrections?: Array<{
    provider?: string;
    page?: number;
    confidence?: number;
    action?: string;
    reason?: string;
    status?: 'applied' | 'suggested' | 'ignored_low_confidence' | string;
    updates?: Record<string, unknown>;
  }>;
  ai_confidence?: number;
  ai_provider?: string;
  ai_review_notes?: string;
  ai_candidate_answer?: string;
  ai_candidate_analysis?: string;
  ai_answer_confidence?: number;
  ai_reasoning_summary?: string;
  ai_knowledge_points?: string[];
  ai_risk_flags?: string[];
  ai_solver_provider?: string;
  ai_solver_model?: string;
  ai_solver_first_model?: string;
  ai_solver_final_model?: string;
  ai_solver_rechecked?: boolean;
  ai_solver_recheck_reason?: string;
  ai_solver_recheck_result?: Record<string, unknown>;
  ai_solver_created_at?: string;
  ai_answer_conflict?: boolean;
  visual_summary?: string;
  visual_confidence?: number;
  visual_parse_status?: 'success' | 'partial' | 'failed' | 'skipped' | string;
  visual_error?: string;
  visual_risk_flags?: string[];
  has_visual_context?: boolean;
  answer_unknown_reason?: string;
  analysis_unknown_reason?: string;
  ai_audit_status?: 'passed' | 'warning' | 'failed' | 'skipped' | string;
  ai_audit_verdict?: string;
  ai_audit_summary?: string;
  ai_can_understand_question?: boolean;
  ai_can_solve_question?: boolean;
  ai_reviewed_before_human?: boolean;
  ai_review_error?: string | null;
  question_quality?: Record<string, unknown>;
  ai_action_logs?: QuestionAiActionLog[];
  material?: {
    id: string;
    content: string;
    images?: Question['images'];
    page_range?: number[];
    image_refs?: string[];
    parse_warnings?: string[];
  };
  pdf_source?: {
    task_id: string;
    file_url: string;
    file_name?: string;
    page_num?: number | null;
    page_range?: number[] | null;
    source_page_start?: number | null;
    source_page_end?: number | null;
    source_bbox?: number[] | null;
    source_anchor_text?: string | null;
    source_confidence?: number | null;
  } | null;
}

export type QuestionAiAction =
  | 'accept_ai_answer'
  | 'accept_ai_analysis'
  | 'accept_ai_both'
  | 'ignore_ai_suggestion';

export interface QuestionAiActionLog {
  id: string;
  question_id: string;
  action: QuestionAiAction;
  field?: string;
  old_value?: string;
  new_value?: string;
  ai_candidate_answer?: string;
  ai_candidate_analysis?: string;
  ai_solver_provider?: string;
  ai_solver_model?: string;
  ai_solver_first_model?: string;
  ai_solver_final_model?: string;
  ai_solver_rechecked?: boolean;
  ai_answer_confidence?: number;
  operator_id?: string;
  created_at?: string;
}

export interface ReviewStats {
  total: number;
  published: number;
  needs_review: number;
  draft: number;
}

export interface ReadabilityReviewResult {
  question_id: string;
  readable: boolean;
  needs_review: boolean;
  marked_needs_review: boolean;
  score: number;
  reasons: string[];
  prompts: string[];
  focus_areas: string[];
  source: string;
  warnings?: string[];
}

export function getQuestions(params?: Record<string, unknown>) {
  return http.get<PageResult<Question>, PageResult<Question>>('/admin/questions', {
    params,
  });
}

export function getQuestion(id: string) {
  return http.get<Question, Question>(`/admin/questions/${id}`);
}

export function updateQuestion(id: string, data: Partial<Question>) {
  return http.put<Question, Question>(`/admin/questions/${id}`, data);
}

export function patchQuestion(id: string, data: Partial<Question>) {
  return http.patch<Question, Question>(`/admin/questions/${id}`, data);
}

export function addQuestionImage(id: string, data: Record<string, unknown>) {
  return http.post<Question, Question>(`/admin/questions/${id}/images`, data);
}

export function reorderQuestionImages(id: string, imageUrls: string[]) {
  return http.patch<Question, Question>(`/admin/questions/${id}/images/reorder`, {
    image_urls: imageUrls,
  });
}

export function mergeQuestionImages(
  id: string,
  data: { image_url: string; next_image_url?: string; same_visual_group_id?: string },
) {
  return http.post<Question, Question>(`/admin/questions/${id}/images/merge`, data);
}

export function deleteQuestionImage(id: string, imageKey: string) {
  return http.delete<Question, Question>(`/admin/questions/${id}/images/${encodeURIComponent(imageKey)}`);
}

export function moveQuestionImage(
  id: string,
  data: { image_url: string; direction?: 'previous' | 'next'; target_question_id?: string },
) {
  return http.post<Question, Question>(`/admin/questions/${id}/move-image`, data);
}

export interface AiRepairProposal {
  content: string;
  options: Partial<Record<'A' | 'B' | 'C' | 'D', string>>;
  visual_refs: Array<Record<string, unknown>>;
  material_text: string;
  remove_texts: string[];
  warnings: string[];
  confidence: number;
  persisted: boolean;
}

export function repairQuestionWithAi(id: string, data: Record<string, unknown> = {}) {
  return http.post<AiRepairProposal, AiRepairProposal>(`/admin/questions/${id}/ai-repair`, data);
}

export function applyQuestionAiAction(id: string, action: QuestionAiAction) {
  return http.post<Question, Question>(`/admin/questions/${id}/ai-action`, { action });
}

export function reviewQuestionReadability(id: string) {
  return http.post<ReadabilityReviewResult, ReadabilityReviewResult>(
    `/admin/questions/${id}/readability-review`,
  );
}

export function deleteQuestion(id: string) {
  return http.delete<boolean, boolean>(`/admin/questions/${id}`);
}

export function batchPublish(ids: string[]) {
  return http.post<{ count: number }, { count: number }>('/admin/questions/batch-publish', {
    ids,
  });
}

export function getReviewStats(bankId: string) {
  return http.get<ReviewStats, ReviewStats>(`/admin/questions/review-stats/${bankId}`);
}
