import http from 'k6/http';
import { check, sleep } from 'k6';

const API = __ENV.STAGING_API_URL;
const TOKEN = __ENV.STAGING_BEARER_TOKEN;

export const options = {
  vus: Number(__ENV.K6_VUS || 5),
  duration: __ENV.K6_DURATION || '2m',
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<4000'],
  },
};

export default function criticalPath() {
  if (!API || !TOKEN) {
    throw new Error('STAGING_API_URL and STAGING_BEARER_TOKEN are required');
  }
  const headers = { Authorization: `Bearer ${TOKEN}` };
  const health = http.get(`${API}/health/ready`);
  check(health, { 'ready': (res) => res.status === 200 });

  const files = http.get(`${API}/api/v1/files?limit=20`, { headers });
  check(files, { 'files inventory': (res) => res.status === 200 });

  const connections = http.get(`${API}/api/v1/connections`, { headers });
  check(connections, { 'connections': (res) => res.status === 200 });
  sleep(1);
}
