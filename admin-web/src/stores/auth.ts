import { defineStore } from 'pinia';
import { getProfile, login as loginApi, logout as logoutApi } from '@/api/auth';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('admin_token') || '',
    userInfo: null as Record<string, unknown> | null,
  }),
  actions: {
    async login(phone: string, password: string) {
      const result = await loginApi(phone, password);
      this.token = result.access_token;
      this.userInfo = result.user;
      localStorage.setItem('admin_token', result.access_token);
      localStorage.setItem('admin_refresh_token', result.refresh_token);
    },
    async fetchProfile() {
      this.userInfo = await getProfile();
    },
    async logout() {
      try {
        await logoutApi();
      } catch {
        // Ignore remote logout failures; local session should still be cleared.
      }
      this.token = '';
      this.userInfo = null;
      localStorage.removeItem('admin_token');
      localStorage.removeItem('admin_refresh_token');
    },
  },
});
