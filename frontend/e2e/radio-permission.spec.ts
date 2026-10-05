import { test, expect } from '@playwright/test';

test('microphone permission precedes voice networking and a failed connection releases the microphone', async ({ page }) => {
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    (window as any).microphoneTracks = [];
    (window as any).microphoneRequests = 0;
    navigator.mediaDevices.getUserMedia = async constraints => {
      (window as any).microphoneRequests++;
      const stream = await original(constraints);
      (window as any).microphoneTracks.push(...stream.getTracks());
      return stream;
    };
  });
  await page.goto('/');
  const headers = { origin: 'http://localhost:8780' };
  await page.request.post('/api/demo/login', { headers, data: { query: 'Microphone permission ' + Date.now() } });
  const trip = await (await page.request.post('/api/trips', { headers, data: {
    title: 'Permission test', starts_at: new Date(Date.now() - 60000).toISOString(), ends_at: new Date(Date.now() + 600000).toISOString()
  } })).json();
  let networkAfterPermission = false;
  await page.route('**/voice-token', async route => {
    networkAfterPermission = await page.evaluate(() => (window as any).microphoneRequests > 0);
    await route.fulfill({ status: 503, json: { detail: 'Test: Sprachserver nicht verfügbar.' } });
  });
  await page.goto('/trip/' + trip.id);
  await expect(page.locator('.radio-status')).toHaveText('FUNK AUS');
  await page.getByRole('button', { name: 'Mikrofon erlauben & Funk verbinden', exact: true }).click();
  await expect(page.locator('.radio-panel').getByRole('alert')).toContainText('Sprachserver nicht verfügbar');
  expect(networkAfterPermission).toBe(true);
  await expect.poll(() => page.evaluate(() => (window as any).microphoneTracks.every((track: MediaStreamTrack) => track.readyState === 'ended'))).toBe(true);
  await expect(page.getByRole('button', { name: 'Mikrofon einschalten', exact: true })).toBeDisabled();
  await expect(page.locator('.radio-status')).toHaveText('FUNK AUS');
});

test('denied microphone permission explains how to enable it and does not contact LiveKit', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('User denied', 'NotAllowedError'); };
  });
  await page.goto('/');
  const headers = { origin: 'http://localhost:8780' };
  await page.request.post('/api/demo/login', { headers, data: { query: 'Denied microphone ' + Date.now() } });
  const trip = await (await page.request.post('/api/trips', { headers, data: {
    title: 'Denied permission test', starts_at: new Date(Date.now() - 60000).toISOString(), ends_at: new Date(Date.now() + 600000).toISOString()
  } })).json();
  let requests = 0;
  await page.route('**/voice-token', route => { requests++; return route.fulfill({ status: 503, json: {} }); });
  await page.goto('/trip/' + trip.id);
  await page.getByRole('button', { name: 'Mikrofon erlauben & Funk verbinden', exact: true }).click();
  await expect(page.locator('.radio-panel').getByRole('alert')).toContainText('Mikrofonzugriff wurde nicht erlaubt');
  expect(requests).toBe(0);
  await expect(page.locator('.radio-status')).toHaveText('FUNK AUS');
});
