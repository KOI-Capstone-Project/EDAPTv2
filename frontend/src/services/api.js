import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

// Global response interceptor — log errors in dev
api.interceptors.response.use(
  res => res,
  err => {
    if (process.env.NODE_ENV === 'development') {
      console.error('[EDAPT API error]', err.response?.status, err.config?.url);
    }
    return Promise.reject(err);
  }
);

export default api;
