import http from './http';

export interface UploadResult {
  url: string;
  filename: string;
}

export function uploadFile(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return http.post<UploadResult, UploadResult>('/admin/upload/file', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}
