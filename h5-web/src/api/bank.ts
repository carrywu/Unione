import http from './http';

export interface Bank {
  id: string;
  name: string;
  subject: string;
  source: string;
  year: number;
  status: string;
  total_count: number;
}

export interface PageResult<T> {
  list: T[];
  total: number;
  page: number;
  pageSize: number;
}

export function getBanks(params?: Record<string, unknown>) {
  return http.get<PageResult<Bank>, PageResult<Bank>>('/api/banks', { params });
}

export function getBankDetail(id: string) {
  return http.get<Bank, Bank>(`/api/banks/${id}`);
}
