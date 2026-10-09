const reconnectLink = document.getElementById('reconnect');
const statusText = document.getElementById('status');
const languageSelect = document.getElementById('offline-language');
const offlineText = {
  de: {settings:'Einstellungen',language:'Sprache',auto:'Automatisch',home:'TeslaTalk – Startseite',title:'Die Verbindung fehlt.',description:'Dein Browser kann den TeslaTalk-Server gerade nicht erreichen. Fahrten, Karte, Sprachfunk und neue Nachrichten sind verfügbar, sobald die Verbindung wieder steht.',reconnect:'Erneut verbinden',checking:'Verbindung wird geprüft …',unavailable:'Der TeslaTalk-Server ist weiterhin nicht erreichbar. Prüfe Verbindung und HTTPS-Zertifikat.',notReady:'Der Server ist noch nicht bereit.',http:'Der Server antwortet mit HTTP '},
  en: {settings:'Settings',language:'Language',auto:'Automatic',home:'TeslaTalk – Home',title:'No connection.',description:'Your browser cannot reach the TeslaTalk server right now. Trips, maps, voice radio and new messages will be available once the connection is restored.',reconnect:'Reconnect',checking:'Checking connection …',unavailable:'The TeslaTalk server is still unreachable. Check the connection and HTTPS certificate.',notReady:'The server is not ready yet.',http:'The server responds with HTTP '},
  nl: {settings:'Instellingen',language:'Taal',auto:'Automatisch',home:'TeslaTalk – Startpagina',title:'Geen verbinding.',description:'Je browser kan de TeslaTalk-server momenteel niet bereiken. Ritten, kaart, spraakradio en nieuwe berichten zijn beschikbaar zodra de verbinding is hersteld.',reconnect:'Opnieuw verbinden',checking:'Verbinding wordt gecontroleerd …',unavailable:'De TeslaTalk-server is nog steeds niet bereikbaar. Controleer de verbinding en het HTTPS-certificaat.',notReady:'De server is nog niet klaar.',http:'De server antwoordt met HTTP '},
  'de-AT': {settings:'Einstellungen',language:'Sprach',auto:'Automatisch',home:'TeslaTalk – Hoam',title:'Oida, ka Verbindung.',description:'Dei Browser kummt grad ned zum TeslaTalk-Server. Fahrten, Kartn, Funk und neue Nachrichten gibt\'s wieder, sobald de Verbindung steht.',reconnect:'No amoi verbinden',checking:'Ma prüfen grad de Verbindung …',unavailable:'Den TeslaTalk-Server erreich ma no immer ned. Schau de Verbindung und des HTTPS-Zertifikat an.',notReady:'Der Server is no ned so weit.',http:'Der Server antwortet mit HTTP '}
};
let offlineMode = 'auto', offlineLanguage = 'en', statusKey = '', httpStatus = 0, connecting = false;
function readLanguage() {
  try { const value = localStorage.getItem('teslatalk-language'); offlineMode = ['de','en','nl','de-AT'].includes(value) ? value : 'auto'; } catch { offlineMode = 'auto'; }
}
function renderLanguage() {
  const detected = (navigator.languages?.length ? navigator.languages : [navigator.language]).map(value => value.toLowerCase().split(/[-_]/)[0]).find(value => ['de','en','nl'].includes(value)) || 'en';
  offlineLanguage = offlineMode === 'auto' ? detected : offlineMode;
  const text = offlineText[offlineLanguage];
  document.documentElement.lang = offlineLanguage;
  document.getElementById('language-label').textContent = text.language;
  document.getElementById('settings-label').textContent = text.settings;
  languageSelect.value = offlineMode;
  languageSelect.options[0].textContent = text.auto + ' · ' + ({de:'Deutsch',en:'English',nl:'Nederlands'})[detected];
  document.querySelector('.brand-logo').setAttribute('aria-label', text.home);
  document.getElementById('offline-title').textContent = text.title;
  document.getElementById('offline-description').textContent = text.description;
  reconnectLink.textContent = text.reconnect;
  statusText.textContent = statusKey ? text[statusKey] + (statusKey === 'http' ? httpStatus + '.' : '') : '';
}
function showStatus(key) { statusKey = key; renderLanguage(); }
readLanguage(); renderLanguage();
languageSelect.addEventListener('change', () => {
  offlineMode = languageSelect.value;
  try { localStorage.setItem('teslatalk-language', offlineMode); } catch { /* Use the selection for this session. */ }
  renderLanguage();
});
window.addEventListener('languagechange', renderLanguage);
window.addEventListener('storage', event => { if (event.key === 'teslatalk-language' || event.key === null) { readLanguage(); renderLanguage(); } });

async function reconnect() {
  if (connecting) return;
  connecting = true;
  reconnectLink.setAttribute('aria-busy', 'true');
  showStatus('checking');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch('/api/health', { cache: 'no-store', signal: controller.signal });
    if (!response.ok) { httpStatus = response.status; showStatus('http'); return; }
    const health = await response.json();
    if (health.status !== 'ok') { showStatus('notReady'); return; }
    if ('serviceWorker' in navigator) {
      const registration = await navigator.serviceWorker.getRegistration();
      if (registration) void registration.update().catch(() => {});
    }
    // Keep trip links; restart sign-in flows rather than replaying OAuth callbacks.
    const target = location.pathname.startsWith('/auth/') || location.pathname === '/offline.html' ? '/' : location.pathname + location.search;
    location.replace(target);
  } catch {
    showStatus('unavailable');
  } finally {
    clearTimeout(timeout);
    connecting = false;
    reconnectLink.removeAttribute('aria-busy');
  }
}

reconnectLink.addEventListener('click', event => { event.preventDefault(); void reconnect(); });
window.addEventListener('online', () => void reconnect());
if (navigator.onLine) void reconnect();
