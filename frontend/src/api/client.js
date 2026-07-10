// Central Axios client with JWT injection and 401 → session-expired redirect.

import axios from 'axios';
import { getToken, logout } from '../utils/auth';

export const SESSION_EXPIRED_KEY = 'session_expired';

const client = axios.create({
  baseURL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

client.interceptors.request.use(config => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      const url = error.config?.url || '';
      if (!url.includes('/api/auth/login')) {
        sessionStorage.setItem(SESSION_EXPIRED_KEY, '1');
      }
      logout();
    }
    if (process.env.NODE_ENV === 'development') {
      console.error('[EDAPT API error]', error.response?.status, error.config?.url);
    }
    return Promise.reject(error);
  }
);

export default client;
