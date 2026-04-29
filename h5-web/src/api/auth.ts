import http from './http';
import type { Bank } from './bank';

export interface AuthResult {
  access_token: string;
  refresh_token: string;
  user: Record<string, unknown>;
}

export function login(phone: string, password: string) {
  return http.post<AuthResult, AuthResult>('/api/auth/login', { phone, password });
}

export function register(phone: string, password: string, nickname: string) {
  return http.post<AuthResult, AuthResult>('/api/auth/register', {
    phone,
    password,
    nickname,
  });
}

export function getProfile() {
  return http.get<Record<string, unknown>, Record<string, unknown>>('/api/user/profile');
}

export function getQuestionBooks() {
  return http.get<Bank[], Bank[]>('/api/user/question-books');
}

export function selectQuestionBooks(bankIds: string[]) {
  return http.put<Bank[], Bank[]>('/api/user/question-books', { bankIds });
}

export function updateAvatar(avatar: string) {
  return http.put<{ avatar: string }, { avatar: string }>('/api/user/avatar', { avatar });
}
