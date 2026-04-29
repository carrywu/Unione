import axios from 'axios';
import { showToast } from 'vant';
import router from '@/router';

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 30000,
});

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('h5_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => {
    const body = response.data;
    if (body && typeof body.code === 'number') {
      if (body.code !== 0) {
        showToast(body.message || '请求失败');
        return Promise.reject(new Error(body.message || '请求失败'));
      }
      return body.data;
    }
    return response.data;
  },
  (error) => {
    const status = error.response?.status;
    const message = error.response?.data?.message || error.message || '请求失败';
    if (status === 401) {
      localStorage.removeItem('h5_token');
      void router.replace('/login');
    }
    showToast(message);
    return Promise.reject(error);
  },
);

export default http;
