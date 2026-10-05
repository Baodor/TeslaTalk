import { test, expect } from '@playwright/test';

test('push notifications replace grouped messages with a renewed alert', async ({ page, context }) => {
  await context.grantPermissions(['notifications']);
  await page.goto('/');
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  const worker = context.serviceWorkers().find(candidate => new URL(candidate.url()).pathname === '/sw.js');
  if (!worker) throw new Error('TeslaTalk service worker is missing.');

  // Exercise the installed push handler and the browser notification store without
  // contacting a push provider. waitUntil is captured for this synthetic event.
  const result = await worker.evaluate(async () => {
    const registration = (globalThis as any).registration as ServiceWorkerRegistration;
    async function receive(body: string, tag: string) {
      const pending: Promise<unknown>[] = [];
      const event = new (globalThis as any).PushEvent('push', { data: JSON.stringify({ title: 'TeslaTalk', body, tag, url: '/' }) });
      Object.defineProperty(event, 'waitUntil', { value: (promise: Promise<unknown>) => pending.push(promise) });
      globalThis.dispatchEvent(event);
      await Promise.all(pending);
    }
    await receive('Erste Nachricht', 'display-test');
    const firstCount = (await registration.getNotifications({ tag: 'display-test' })).length;
    await receive('Zweite Nachricht', 'display-test');
    const notifications = await registration.getNotifications({ tag: 'display-test' });
    const grouped = notifications.map(notification => ({
      body: notification.body, icon: notification.icon,
      silent: notification.silent, renotify: notification.renotify,
    }));
    await receive('Nachricht ohne Tag', '');
    const fallbackCount = (await registration.getNotifications({ tag: 'teslatalk' })).length;
    for (const notification of await registration.getNotifications()) notification.close();
    return { firstCount, grouped, fallbackCount };
  });
  expect(result.firstCount).toBe(1);
  expect(result.grouped).toEqual([{
    body: 'Zweite Nachricht', silent: false, renotify: true,
    icon: 'http://localhost:8780/icons/icon-192.png',
  }]);
  expect(result.fallbackCount).toBe(1);
});
