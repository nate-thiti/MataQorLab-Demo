import axios from 'axios';
import { getPublicApiUrl } from './env.js';
import { supabase } from './supabaseClient.js';
import { correlationHeaders } from './correlation.js';

const api = axios.create({
  baseURL: getPublicApiUrl(),
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(
  async (config) => {
    config.headers = correlationHeaders(config.headers || {});
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) {
      config.headers.Authorization = `Bearer ${session.access_token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message;
    error.incidentId = error.response?.data?.incident_id
      || error.response?.headers?.['x-correlation-id']
      || error.response?.headers?.['x-request-id']
      || null;
    error.errorCode = error.response?.data?.error_code || null;
    console.error('API Error:', message, error.incidentId ? `(incident ${error.incidentId})` : '');
    return Promise.reject(error);
  },
);

export default api;
