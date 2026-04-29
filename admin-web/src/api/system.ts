import http from './http';

export interface SystemConfig {
  id: string;
  key: string;
  value: string;
  description?: string;
  value_type: 'string' | 'number' | 'boolean' | 'json';
  updated_at: string;
}

export function getSystemConfigs() {
  return http.get<SystemConfig[], SystemConfig[]>('/admin/system/configs');
}

export function updateSystemConfig(key: string, data: { value: string; description?: string }) {
  return http.put<SystemConfig, SystemConfig>(`/admin/system/configs/${key}`, data);
}

export function getSystemInfo() {
  return http.get<Record<string, unknown>, Record<string, unknown>>('/admin/system/info');
}
