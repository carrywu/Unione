import http from './http';

export interface PdfServiceStatus {
  status: string;
  reachable: boolean;
  response_ms: number;
  uptime_seconds?: number;
  version?: string;
  queue?: { pending: number; processing: number; completed_today: number };
  memory_mb?: number;
  ai_providers?: Record<string, { enabled: boolean; last_call_at?: string | null; last_error?: string | null }>;
  error?: string;
}

export interface PdfServiceStats {
  today?: {
    total_parsed: number;
    total_questions: number;
    success_count: number;
    fail_count: number;
    avg_questions_per_pdf: number;
    avg_parse_seconds: number;
  };
  session?: {
    total_parsed: number;
    total_questions: number;
    ai_calls: Record<string, number>;
  };
}

export interface PdfServiceConfig {
  ai_provider_vision: string;
  ai_provider_text: string;
  qwen_api_key_set: boolean;
  deepseek_api_key_set: boolean;
  backend_url: string;
  prompt_source: string;
  cache_ttl: number;
}

export interface TestParseResult {
  questions: any[];
  materials: any[];
  stats: Record<string, any>;
  detection?: Record<string, any>;
}

export const pdfServiceApi = {
  getStatus: () => http.get<PdfServiceStatus, PdfServiceStatus>('/admin/pdf-service/status'),
  getStats: () => http.get<PdfServiceStats, PdfServiceStats>('/admin/pdf-service/stats'),
  getConfig: () => http.get<PdfServiceConfig, PdfServiceConfig>('/admin/pdf-service/config'),
  updateConfig: (data: Record<string, unknown>) =>
    http.put<{ updated: string[] }, { updated: string[] }>('/admin/pdf-service/config', data),
  invalidateCache: () => http.post<{ cleared: boolean }, { cleared: boolean }>('/admin/pdf-service/cache-invalidate'),
  testParse: (data: { bank_id?: string; file_url: string; pages?: number[] }) =>
    http.post<TestParseResult, TestParseResult>('/admin/pdf-service/test-parse', data, { timeout: 5 * 60 * 1000 }),
};
