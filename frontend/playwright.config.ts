import { defineConfig } from '@playwright/test';
import path from 'node:path';
const proxyUrl=process.env.HTTPS_PROXY ? new URL(process.env.HTTPS_PROXY) : null;
export default defineConfig({
  testDir: './e2e', workers: 1, timeout: 30000,
  use: { baseURL: 'http://localhost:8780', viewport: { width: 1440, height: 960 }, trace: 'retain-on-failure',
    ignoreHTTPSErrors: Boolean(proxyUrl),
    launchOptions: { executablePath: process.env.TT_BROWSER_PATH || undefined,
      proxy: proxyUrl ? { server: proxyUrl.origin, bypass: 'localhost,127.0.0.1', username: decodeURIComponent(proxyUrl.username), password: decodeURIComponent(proxyUrl.password) } : undefined,
      args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] } },
  webServer: {
    command: 'python -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 8780 --no-access-log',
    url: 'http://localhost:8780/api/health', reuseExistingServer: !process.env.CI,
    env: { APP_URL: 'http://localhost:8780', DEMO_MODE: 'true',
      APP_SECRET: 'only-for-isolated-browser-tests-'+'a'.repeat(40),
      DB_PATH: path.resolve('../test-results/browser.sqlite'), FRONTEND_DIR: path.resolve('dist'),
      LIVEKIT_INTERNAL_URL: 'http://127.0.0.1:7880', LIVEKIT_URL: 'ws://localhost:7880',
      LIVEKIT_API_KEY: process.env.LIVEKIT_API_KEY || '', LIVEKIT_API_SECRET: process.env.LIVEKIT_API_SECRET || '' }
  }
});
