import { authFetch } from './authFetch.js';
import { getPublicApiUrl } from './env.js';

const endpoint = (path) => `${getPublicApiUrl()}/api/v1/customer-experience${path}`;

export async function customerExperienceRequest(path, options = {}) {
  const response = await authFetch(endpoint(path), options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || 'Customer experience request failed');
  }
  return payload;
}
