import { useEffect, useRef, useState } from 'react';
import { Bell, BellOff, Download, RefreshCw, X } from 'lucide-react';
import { api } from './api';

type InstallPrompt = Event & { prompt(): Promise<void>; userChoice: Promise<{ outcome: string }> };
const standalone = () => matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
const supported = () => 'Notification' in window && 'serviceWorker' in navigator && 'PushManager' in window;
function applicationKey(value: string) {
  const data = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4));
  return Uint8Array.from(data, character => character.charCodeAt(0));
}
function preference(userId: string) {
  try { return localStorage.getItem('teslatalk-push:' + userId); } catch { return null; }
}
function remember(userId: string, enabled: boolean) {
  try { localStorage.setItem('teslatalk-push:' + userId, enabled ? 'on' : 'off'); } catch { /* Private browsing may disable storage. */ }
}

// Stay mounted after sign-in, even when the profile is closed. Rebind an existing
// device subscription to the current session; a network failure never revokes consent.
export function usePWAControls(config: any, userId: string | undefined, notify: (text: string) => void) {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null), [installed, setInstalled] = useState(standalone());
  const [help, setHelp] = useState(false), [enabled, setEnabled] = useState(false), [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false), [needsRepair, setNeedsRepair] = useState(false), [status, setStatus] = useState('');
  const busyRef = useRef(false), revision = useRef(0), retryRef = useRef<() => void>(() => {});
  useEffect(() => {
    const before = (event: Event) => { event.preventDefault(); setPrompt(event as InstallPrompt); };
    const done = () => { setInstalled(true); setPrompt(null); };
    window.addEventListener('beforeinstallprompt', before); window.addEventListener('appinstalled', done);
    return () => { window.removeEventListener('beforeinstallprompt', before); window.removeEventListener('appinstalled', done); };
  }, []);
  useEffect(() => {
    revision.current++;
    setEnabled(Boolean(userId && preference(userId) === 'on')); setStatus(''); setNeedsRepair(false);
    if (!userId || !supported() || !config.push_ready) {
      if (userId) {
        setNeedsRepair(preference(userId) === 'on');
        setStatus(!supported() ? 'Dieser Browser unterstützt Web-Push hier nicht. Auf dem iPhone TeslaTalk über das Home-Bildschirm-Symbol öffnen.' : 'Der Betreiber muss Web-Push auf dem Server einrichten. Deine Auswahl bleibt gespeichert.');
      }
      setChecking(false); return;
    }
    let cancelled = false, syncing = false, lastAttempt = 0;
    async function sync(force = false) {
      if (cancelled || syncing || busyRef.current || (!force && Date.now() - lastAttempt < 60000)) return;
      syncing = true; lastAttempt = Date.now();
      const version = revision.current;
      const current = () => !cancelled && version === revision.current;
      try {
        if (Notification.permission !== 'granted') {
          if (current()) {
            const wanted = preference(userId!) === 'on';
            setEnabled(wanted); setNeedsRepair(wanted);
            setStatus(Notification.permission === 'denied' ? 'Im Browser blockiert. Erlaube Benachrichtigungen in den Geräte- oder Browser-Einstellungen.' : 'Auf diesem Gerät noch nicht freigegeben.');
          }
          return;
        }
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.getSubscription();
        if (!current()) return;
        if (preference(userId!) === 'off') {
          setEnabled(false);
          if (subscription) {
            await subscription.unsubscribe();
            await api('/api/push/unsubscribe', 'POST', { endpoint: subscription.endpoint });
          }
          return;
        }
        if (!subscription) {
          const wanted = preference(userId!) === 'on';
          setEnabled(wanted); setNeedsRepair(wanted);
          setStatus(wanted ? 'Dein Browser-Abonnement fehlt. Aktiviere es erneut; deine Einstellung bleibt gespeichert.' : 'Benachrichtigungen sind auf diesem Gerät ausgeschaltet.');
          return;
        }
        // Browser permission and subscription establish local state before contacting
        // the server. An unavailable backend must not turn the setting off.
        remember(userId!, true); setEnabled(true); setNeedsRepair(false);
        await api('/api/push/subscribe', 'POST', subscription.toJSON());
        if (current()) setStatus('Auf diesem Gerät aktiviert.');
      } catch {
        if (current()) setStatus('Der Serverabgleich steht aus. Deine Einstellung bleibt gespeichert; versuche es erneut, sobald die Verbindung steht.');
      } finally {
        syncing = false;
        if (current()) setChecking(false);
      }
    }
    setChecking(true); void sync(true);
    const resume = () => { if (document.visibilityState === 'visible') void sync(); };
    const online = () => void sync(true);
    retryRef.current = () => void sync(true);
    window.addEventListener('focus', resume); window.addEventListener('online', online); document.addEventListener('visibilitychange', resume);
    return () => {
      cancelled = true; retryRef.current = () => {};
      window.removeEventListener('focus', resume); window.removeEventListener('online', online); document.removeEventListener('visibilitychange', resume);
    };
  }, [config.push_ready, userId]);

  async function install() {
    if (prompt) { await prompt.prompt(); await prompt.userChoice; setPrompt(null); }
    else setHelp(true);
  }
  async function togglePush(disable = false) {
    if (!userId || busyRef.current) return;
    const turnOff = disable || (enabled && !needsRepair);
    if (!config.push_ready && !turnOff) { notify('Der Betreiber muss Web-Push in der Serverkonfiguration einrichten.'); return; }
    if (!supported()) {
      if (turnOff) { remember(userId, false); setEnabled(false); setNeedsRepair(false); }
      else setHelp(true);
      return;
    }
    busyRef.current = true; revision.current++; setBusy(true);
    try {
      if (!turnOff) {
        // Request permission directly from the tap, before asynchronous work.
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
          const wanted = preference(userId) === 'on';
          setEnabled(wanted); setNeedsRepair(wanted);
          setStatus('Nicht freigegeben. Erlaube Benachrichtigungen in den Geräte- oder Browser-Einstellungen.');
          return;
        }
      }
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (turnOff) {
        if (subscription && !await subscription.unsubscribe()) throw new Error('Das Browser-Abonnement konnte nicht deaktiviert werden. Bitte erneut versuchen.');
        remember(userId, false); setEnabled(false); setNeedsRepair(false); setStatus('Auf diesem Gerät ausgeschaltet.');
        if (subscription) await api('/api/push/unsubscribe', 'POST', { endpoint: subscription.endpoint });
        notify('Benachrichtigungen auf diesem Gerät deaktiviert.');
      } else {
        subscription ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: applicationKey(config.vapid_public_key) });
        remember(userId, true); setEnabled(true); setNeedsRepair(false);
        setStatus('Browser freigegeben. Serverabgleich läuft …');
        await api('/api/push/subscribe', 'POST', subscription.toJSON());
        setStatus('Auf diesem Gerät aktiviert.');
        notify('Benachrichtigungen für Nachrichten, Einladungen und Freundschaftsanfragen aktiviert.');
      }
    } catch (error) {
      setStatus(turnOff && preference(userId) === 'off' ? 'Im Browser ausgeschaltet. Der Serverabgleich ist fehlgeschlagen.' : 'Der Serverabgleich steht aus. Deine Einstellung bleibt gespeichert; versuche es erneut.');
      notify((error as Error).message || 'Benachrichtigungen konnten nicht eingerichtet werden.');
    } finally { busyRef.current = false; setBusy(false); setChecking(false); }
  }
  return { installed, help, setHelp, enabled, busy, checking, needsRepair, status, install, togglePush, retry: () => retryRef.current() };
}
export type PWAState = ReturnType<typeof usePWAControls>;

export default function PWAControls({ controls }: { controls: PWAState }) {
  const { installed, help, setHelp, enabled, busy, checking, needsRepair, status, install, togglePush, retry } = controls;
  return <section className="panel personal-notifications" aria-label="Benachrichtigungen und Web-App">
    <div className="panel-heading"><Bell size={21} /><h3>Benachrichtigungen & Web-App</h3></div>
    <p>Deine Einstellung gilt für dieses Gerät. Du erhältst Hinweise zu Nachrichten, Einladungen und Freundschaftsanfragen.</p>
    <div className="pwa-controls">
      <button onClick={() => void togglePush()} disabled={busy || checking} aria-pressed={enabled}>{enabled ? <Bell size={16} /> : <BellOff size={16} />}<span>{busy || checking ? 'Wird geprüft …' : needsRepair ? 'Benachrichtigungen erneut aktivieren' : enabled ? 'Benachrichtigungen an' : 'Benachrichtigungen'}</span></button>
      {needsRepair ? <button onClick={() => void togglePush(true)} disabled={busy}>Deaktivieren</button> : enabled && <button onClick={retry} disabled={busy || checking}><RefreshCw size={16} />Erneut abgleichen</button>}
      {!installed && <button onClick={() => void install()}><Download size={16} /><span>Zum Home-Bildschirm</span></button>}
      {help && <div className="install-help" role="dialog" aria-label="TeslaTalk installieren"><button className="icon-button" aria-label="Schließen" onClick={() => setHelp(false)}><X size={18} /></button><strong>Dein Roadtrip auf dem Home-Bildschirm</strong><p><b>iPhone / iPad:</b> Öffne TeslaTalk in Safari. Wähle Teilen → Zum Home-Bildschirm. Starte TeslaTalk anschließend über das neue Symbol und aktiviere Benachrichtigungen.</p><p><b>Android / Desktop:</b> Wähle im Browser-Menü „App installieren“ oder „Zum Startbildschirm hinzufügen“.</p><small>Web-Push braucht HTTPS und einen unterstützten Browser. Auf iPhone / iPad wird iOS / iPadOS 16.4 oder neuer benötigt. Sprachfunk braucht eine aktive Internetverbindung.</small></div>}
    </div>
    <p className="notification-status hint" role="status">{status || 'Auf diesem Gerät ausgeschaltet.'}</p>
  </section>;
}
