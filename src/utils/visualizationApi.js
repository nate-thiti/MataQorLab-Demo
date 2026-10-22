import { authFetch } from './authFetch.js';
import { getPublicApiUrl } from './env.js';
import { backendIncident } from './correlation.js';

const endpoint = (path) => `${getPublicApiUrl()}/api/v1/visualizations${path}`;

export async function visualizationRequest(path, options = {}) {
  const response = await authFetch(endpoint(path), options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.detail || 'Visualization request failed');
    Object.assign(error, backendIncident(payload, response));
    throw error;
  }
  return payload;
}
