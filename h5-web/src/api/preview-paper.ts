import http from './http';
import type { Question } from './question';
import type { SubmitPayload } from './record';

export interface PreviewPaper {
  paper_id: string;
  task_id: string;
  source_bank_id?: string;
  title: string;
  preview_only: boolean;
  publish_status: string;
  production_published: boolean;
  question_count: number;
  debug_dir?: string | null;
  created_at?: string;
  updated_at?: string;
  questions: Question[];
}

export interface PreviewSubmitResponse {
  is_correct: boolean;
  answer?: string | null;
  analysis?: string | null;
  answer_unknown_reason?: string | null;
  analysis_unknown_reason?: string | null;
  analysis_image_url?: string | null;
  analysis_image_urls?: string[];
  visual_summary?: string | null;
  ai_audit_summary?: string | null;
}

export function getPreviewPaper(paperId: string) {
  return http.get<PreviewPaper, PreviewPaper>(`/api/preview-papers/${paperId}`);
}

export function submitPreviewPaperAnswer(paperId: string, data: SubmitPayload) {
  return http.post<PreviewSubmitResponse, PreviewSubmitResponse>(
    `/api/preview-papers/${paperId}/submit`,
    data,
  );
}
