import http from './http';

export interface Bank {
  id: string;
  name: string;
  subject: string;
  source: string;
  year: number;
  status: 'draft' | 'published';
  total_count: number;
  created_at: string;
}

export interface PageResult<T> {
  list: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface BankPayload {
  name: string;
  subject: string;
  source?: string;
  year: number;
}

export function getBanks(params?: Record<string, unknown>) {
  return http.get<PageResult<Bank>, PageResult<Bank>>('/admin/banks', { params });
}

export function getBankDetail(id: string) {
  return http.get<Bank, Bank>(`/api/banks/${id}`);
}

export function createBank(data: BankPayload) {
  return http.post<Bank, Bank>('/admin/banks', data);
}

export function updateBank(id: string, data: Partial<BankPayload>) {
  return http.put<Bank, Bank>(`/admin/banks/${id}`, data);
}

export function deleteBank(id: string) {
  return http.delete<boolean, boolean>(`/admin/banks/${id}`);
}

export function publishBank(id: string) {
  return http.put<Bank, Bank>(`/admin/banks/${id}/publish`);
}
