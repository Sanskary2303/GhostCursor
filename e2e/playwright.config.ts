import { defineConfig } from '@playwright/test';
import path from 'node:path';

const root = path.resolve(__dirname, '..');
const py = path.join(root, '.venv/bin/python');

const testKey = 'test-key-shophive-demo-0123456789abcdef';
const sharedEnv = {
  ...process.env,
  GHOST_CURSOR_API_KEY: testKey,
  GHOST_TENANT_KEYS: JSON.stringify({ [testKey]: 'shophive_demo' }),
  GHOST_PROVIDER: 'mock',
  GHOST_STORE: 'memory',
  GHOST_RATE_LIMIT_PER_MIN: '100000',
};

export default defineConfig({
  testDir: '.',
  timeout: 60_000,
  use: { baseURL: 'http://127.0.0.1:8081', trace: 'retain-on-failure' },
  webServer: [
    { command: `"${py}" -m uvicorn app.main:app --port 8080`, cwd: path.join(root, 'services/orchestrator'), url: 'http://127.0.0.1:8080/health', reuseExistingServer: !process.env.CI, env: sharedEnv },
    { command: `"${py}" -m uvicorn main:app --port 8081`, cwd: path.join(root, 'demo/shophive/backend'), url: 'http://127.0.0.1:8081/health', reuseExistingServer: !process.env.CI, env: sharedEnv },
  ],
});
