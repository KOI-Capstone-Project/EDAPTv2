import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

// Attach JWT on every request if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('edapt_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  res => res,
  err => {
    console.error('[EDAPT API]', err.response?.status ?? 'network error', err.config?.url);
    return Promise.reject(err);
  }
);

export default api;
