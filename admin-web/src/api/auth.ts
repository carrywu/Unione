import http from './http';

export interface LoginResult {
  access_token: string;
  refresh_token: string;
  user: Record<string, unknown>;
}

export function login(phone: string, password: string) {
  return http.post<LoginResult, LoginResult>('/api/auth/login', { phone, password });
}

export function logout() {
  return http.post<boolean, boolean>('/api/auth/logout');
}

export function getProfile() {
  return http.get<Record<string, unknown>, Record<string, unknown>>('/api/user/profile');
}
