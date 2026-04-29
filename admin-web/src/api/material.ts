import http from './http';
import type { PageResult } from './bank';
import type { Question } from './question';

export interface Material {
  id: string;
  bank_id: string;
  content: string;
  images?: unknown[];
  question_count?: number;
  questions?: Question[];
  created_at?: string;
}

export function getMaterials(params: Record<string, unknown>) {
  return http.get<PageResult<Material>, PageResult<Material>>('/admin/materials', { params });
}

export function getMaterialDetail(id: string) {
  return http.get<Material, Material>(`/admin/materials/${id}`);
}

export function updateMaterial(id: string, data: Partial<Material>) {
  return http.put<Material, Material>(`/admin/materials/${id}`, data);
}

export function deleteMaterial(id: string) {
  return http.delete<{ deleted: boolean; unlinked_questions: number }, { deleted: boolean; unlinked_questions: number }>(
    `/admin/materials/${id}`,
  );
}
