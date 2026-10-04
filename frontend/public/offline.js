const reconnectLink = document.getElementById('reconnect');
const statusText = document.getElementById('status');
let connecting = false;

async function reconnect() {
  if (connecting) return;
  connecting = true;
  reconnectLink.setAttribute('aria-busy', 'true');
  statusText.textContent = 'Verbindung wird geprüft …';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch('/api/health', { cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error('Der Server antwortet mit HTTP ' + response.status + '.');
    const health = await response.json();
    if (health.status !== 'ok') throw new Error('Der Server ist noch nicht bereit.');
    if ('serviceWorker' in navigator) {
      const registration = await navigator.serviceWorker.getRegistration();
      if (registration) void registration.update().catch(() => {});
    }
    // Keep trip links; restart sign-in flows rather than replaying OAuth callbacks.
    const target = location.pathname.startsWith('/auth/') || location.pathname === '/offline.html' ? '/' : location.pathname + location.search;
    location.replace(target);
  } catch (error) {
    statusText.textContent = error instanceof TypeError || controller.signal.aborted
      ? 'Der TeslaTalk-Server ist weiterhin nicht erreichbar. Prüfe Verbindung und HTTPS-Zertifikat.'
      : error.message;
  } finally {
    clearTimeout(timeout);
    connecting = false;
    reconnectLink.removeAttribute('aria-busy');
  }
}

reconnectLink.addEventListener('click', event => { event.preventDefault(); void reconnect(); });
window.addEventListener('online', () => void reconnect());
if (navigator.onLine) void reconnect();
