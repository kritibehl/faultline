import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 16,
  duration: '30s',
};

const token = __ENV.INSPECTOR_TOKEN || 'test-token';

export default function () {
  const health = http.get('http://localhost:8088/health');
  check(health, {
    'health reachable': (r) => r.status === 200,
  });

  const leases = http.get('http://localhost:8088/leases', {
    headers: { Authorization: `Bearer ${token}` },
  });
  check(leases, {
    'leases reachable': (r) => r.status === 200 || r.status === 401,
  });

  const metrics = http.get('http://localhost:8088/metrics', {
    headers: { Authorization: `Bearer ${token}` },
  });
  check(metrics, {
    'metrics reachable': (r) => r.status === 200 || r.status === 401,
  });

  sleep(1);
}
