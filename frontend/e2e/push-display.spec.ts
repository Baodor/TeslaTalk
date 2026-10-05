import { test, expect } from '@playwright/test';

test('push handler requests renewed alerts and handles missing tags', async ({ page, context }) => {
  await page.goto('/');
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  const worker = context.serviceWorkers().find(candidate => new URL(candidate.url()).pathname === '/sw.js');
  if (!worker) throw new Error('TeslaTalk service worker is missing.');

  // Exercise the installed handler while capturing the native notification call.
  // Headless Chromium denies OS notifications even with granted permissions.
  const result = await worker.evaluate(async () => {
    const registration = (globalThis as any).registration as ServiceWorkerRegistration;
    const originalShowNotification = registration.showNotification;
    const requests: { title: string; options: NotificationOptions }[] = [];
    registration.showNotification = async (title, options = {}) => {
      requests.push({ title, options });
    };
    async function receive(body: string, tag: unknown) {
      const pending: Promise<unknown>[] = [];
      const event = new (globalThis as any).PushEvent('push', { data: JSON.stringify({ title: 'TeslaTalk', body, tag, url: '/' }) });
      Object.defineProperty(event, 'waitUntil', { value: (promise: Promise<unknown>) => pending.push(promise) });
      globalThis.dispatchEvent(event);
      await Promise.all(pending);
    }
    try {
      await receive('Erste Nachricht', 'display-test');
      await receive('Zweite Nachricht', 'display-test');
      for (const tag of ['', null, 42, ' ']) await receive('Nachricht ohne Tag', tag);
      return requests;
    } finally {
      registration.showNotification = originalShowNotification;
    }
  });
  expect(result).toEqual(['Erste Nachricht', 'Zweite Nachricht', ...Array(4).fill('Nachricht ohne Tag')].map((body, index) => ({
    title: 'TeslaTalk', options: {
      body, tag: index < 2 ? 'display-test' : 'teslatalk',
      icon: '/icons/icon-192.png', data: { url: '/' },
      silent: false, renotify: true,
    },
  })));
});
