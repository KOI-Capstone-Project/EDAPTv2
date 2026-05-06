import axios from 'axios';
import { getToken, logout } from '../utils/auth';

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
      logout();
    }
    if (process.env.NODE_ENV === 'development') {
      console.error('[EDAPT API error]', error.response?.status, error.config?.url);
    }
    return Promise.reject(error);
  }
);

export default client;
