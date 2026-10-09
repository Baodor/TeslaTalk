/* Cache public assets only. Accounts, trips, chat and GPS are never cached. */
const CACHE = 'teslatalk-public-v8';
const PUBLIC_ASSETS = ['/offline.html', '/offline.css', '/offline.js', '/viewport.js', '/favicon.svg', '/favicon.ico', '/favicon-32-v6.png', '/favicon-64-v6.png', '/icons/icon-192.png', '/icons/apple-touch-icon.png', '/apple-touch-icon.png', '/apple-touch-icon-v4.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC_ASSETS)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('teslatalk-public-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request, { cache: 'no-store' }).catch(async () => {
      const cached = await caches.match('/offline.html');
      const headers = new Headers(cached.headers);
      // A temporary offline document must not be retained as the application page.
      headers.set('Cache-Control', 'no-store');
      headers.set('X-TeslaTalk-Offline', '1');
      headers.delete('ETag'); headers.delete('Last-Modified');
      return new Response(cached.body, { headers });
    }));
  } else if (PUBLIC_ASSETS.includes(url.pathname)) {
    event.respondWith(caches.match(event.request, { ignoreSearch: true }).then(cached => cached || fetch(event.request)));
  } else if (url.pathname.startsWith('/assets/')) {
    event.respondWith(caches.open(CACHE).then(async cache => {
      const cached = await cache.match(event.request);
      if (cached) return cached;
      const response = await fetch(event.request);
      if (response.ok) await cache.put(event.request, response.clone());
      return response;
    }));
  }
});
self.addEventListener('push', event => {
  const language = (navigator.languages || [navigator.language]).map(value => value.toLowerCase().split('-')[0]).find(value => ['de','en','nl'].includes(value)) || 'en';
  const fallback = {de:'Es gibt Neuigkeiten für deine Fahrt.',en:'There are updates for your trip.',nl:'Er is nieuws over je rit.'};
  let data = { title: 'TeslaTalk', body: fallback[language], url: '/', tag: 'teslatalk' };
  try { data = { ...data, ...event.data.json() }; } catch (_) {}
  // Replacing a grouped message should alert again. renotify requires a nonempty tag.
  const tag = typeof data.tag === 'string' && data.tag.trim() ? data.tag : 'teslatalk';
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body, tag, icon: '/icons/icon-192.png',
    data: { url: data.url }, silent: false, renotify: true
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  let target = new URL('/', self.location.origin);
  try {
    const requested = new URL(event.notification.data?.url || '/', self.location.origin);
    if (requested.origin === self.location.origin) target = requested;
  } catch (_) {}
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async clients => {
    for (const client of clients) {
      if ('navigate' in client) { await client.navigate(target.href); return client.focus(); }
    }
    return self.clients.openWindow(target.href);
  }));
});
