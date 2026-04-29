import { defineStore } from 'pinia';
import { getProfile, login as loginApi, register as registerApi } from '@/api/auth';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('h5_token') || '',
    userInfo: null as Record<string, unknown> | null,
  }),
  actions: {
    async login(phone: string, password: string) {
      const result = await loginApi(phone, password);
      this.token = result.access_token;
      this.userInfo = result.user;
      localStorage.setItem('h5_token', result.access_token);
      localStorage.setItem('h5_refresh_token', result.refresh_token);
    },
    async register(phone: string, password: string, nickname: string) {
      const result = await registerApi(phone, password, nickname);
      this.token = result.access_token;
      this.userInfo = result.user;
      localStorage.setItem('h5_token', result.access_token);
      localStorage.setItem('h5_refresh_token', result.refresh_token);
    },
    async fetchProfile() {
      this.userInfo = await getProfile();
    },
    logout() {
      this.token = '';
      this.userInfo = null;
      localStorage.removeItem('h5_token');
      localStorage.removeItem('h5_refresh_token');
    },
  },
});
