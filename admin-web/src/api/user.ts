import http from './http';
import type { PageResult } from './bank';

export interface AdminUser {
  id: string;
  phone: string;
  nickname: string;
  avatar: string;
  role: 'user' | 'admin';
  is_active: boolean;
  last_login_at?: string;
  last_login_ip?: string;
  created_at: string;
  updated_at: string;
}

export function getUsers(params?: Record<string, unknown>) {
  return http.get<PageResult<AdminUser>, PageResult<AdminUser>>('/admin/users', {
    params,
  });
}

export function updateUser(id: string, data: Partial<AdminUser>) {
  return http.put<AdminUser, AdminUser>(`/admin/users/${id}`, data);
}

export function deleteUser(id: string) {
  return http.delete<boolean, boolean>(`/admin/users/${id}`);
}

export function toggleUserActive(id: string) {
  return http.put<{ id: string; is_active: boolean; message: string }, { id: string; is_active: boolean; message: string }>(
    `/admin/users/${id}/toggle-active`,
  );
}

export function resetUserPassword(id: string, newPassword: string) {
  return http.put<null, null>(`/admin/users/${id}/reset-password`, {
    new_password: newPassword,
  });
}

export function getUserRecords(id: string, params?: Record<string, unknown>) {
  return http.get(`/admin/users/${id}/records`, { params });
}

export function getUserStats(id: string) {
  return http.get<Record<string, unknown>, Record<string, unknown>>(`/admin/users/${id}/stats`);
}
