import { defineConfig } from '@playwright/test';
import path from 'node:path';

const root = path.resolve(__dirname, '..');
const py = path.join(root, '.venv/bin/python');

export default defineConfig({
  testDir: '.',
  timeout: 60_000,
  use: { baseURL: 'http://127.0.0.1:8081', trace: 'retain-on-failure' },
  webServer: [
    { command: `"${py}" -m uvicorn app.main:app --port 8080`, cwd: path.join(root, 'services/orchestrator'), url: 'http://127.0.0.1:8080/health', reuseExistingServer: !process.env.CI },
    { command: `"${py}" -m uvicorn main:app --port 8081`, cwd: path.join(root, 'demo/shophive/backend'), url: 'http://127.0.0.1:8081/health', reuseExistingServer: !process.env.CI },
  ],
});

