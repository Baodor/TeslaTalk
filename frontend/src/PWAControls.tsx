import { useEffect, useState } from 'react';
import { Bell, BellOff, Download, X } from 'lucide-react';
import { api } from './api';

type InstallPrompt = Event & { prompt(): Promise<void>; userChoice: Promise<{ outcome: string }> };
const standalone = () => matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
const supported = () => 'Notification' in window && 'serviceWorker' in navigator && 'PushManager' in window;
function applicationKey(value: string) {
  const data = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4));
  return Uint8Array.from(data, character => character.charCodeAt(0));
}

export default function PWAControls({ config, notify }: { config: any; notify: (text: string) => void }) {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null), [installed, setInstalled] = useState(standalone());
  const [help, setHelp] = useState(false), [enabled, setEnabled] = useState(false), [busy, setBusy] = useState(false);
  useEffect(() => {
    const before = (event: Event) => { event.preventDefault(); setPrompt(event as InstallPrompt); };
    const done = () => { setInstalled(true); setPrompt(null); };
    window.addEventListener('beforeinstallprompt', before);
    window.addEventListener('appinstalled', done);
    if (supported() && config.push_ready && Notification.permission === 'granted') {
      void navigator.serviceWorker.ready.then(async registration => {
        const subscription = await registration.pushManager.getSubscription();
        if (subscription) { await api('/api/push/subscribe', 'POST', subscription.toJSON()); setEnabled(true); }
      }).catch(() => setEnabled(false));
    }
    return () => { window.removeEventListener('beforeinstallprompt', before); window.removeEventListener('appinstalled', done); };
  }, [config.push_ready]);

  async function install() {
    if (prompt) { await prompt.prompt(); await prompt.userChoice; setPrompt(null); }
    else setHelp(true);
  }
  async function togglePush() {
    if (!config.push_ready) { notify('Der Betreiber muss Web-Push in der Serverkonfiguration einrichten.'); return; }
    if (!supported()) { setHelp(true); return; }
    setBusy(true);
    try {
      if (!enabled) {
        // Request permission directly from the user gesture, before asynchronous work.
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') { notify('Benachrichtigungen sind nicht freigegeben. Du kannst sie in den Browser-Einstellungen erlauben.'); return; }
      }
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (enabled) {
        if (subscription) { await api('/api/push/unsubscribe', 'POST', { endpoint: subscription.endpoint }); await subscription.unsubscribe(); }
        setEnabled(false); notify('Benachrichtigungen auf diesem Gerät deaktiviert.');
      } else {
        subscription ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: applicationKey(config.vapid_public_key) });
        await api('/api/push/subscribe', 'POST', subscription.toJSON());
        setEnabled(true); notify('Benachrichtigungen für Nachrichten, Einladungen und Freundschaftsanfragen aktiviert.');
      }
    } catch (error) { notify((error as Error).message || 'Benachrichtigungen konnten nicht aktiviert werden.'); }
    finally { setBusy(false); }
  }
  return <div className="pwa-controls">
    {!installed && <button onClick={() => void install()}><Download size={16} /><span>Zum Home-Bildschirm</span></button>}
    <button onClick={() => void togglePush()} disabled={busy} aria-pressed={enabled} title={enabled ? 'Benachrichtigungen deaktivieren' : 'Benachrichtigungen aktivieren'}>{enabled ? <Bell size={16} /> : <BellOff size={16} />}<span>{busy ? 'Wird eingerichtet …' : enabled ? 'Benachrichtigungen an' : 'Benachrichtigungen'}</span></button>
    {help && <div className="install-help" role="dialog" aria-label="TeslaTalk installieren"><button className="icon-button" aria-label="Schließen" onClick={() => setHelp(false)}><X size={18} /></button><strong>Dein Roadtrip auf dem Home-Bildschirm</strong><p><b>iPhone / iPad:</b> Öffne TeslaTalk in Safari. Wähle Teilen → Zum Home-Bildschirm. Starte TeslaTalk anschließend über das neue Symbol und aktiviere Benachrichtigungen.</p><p><b>Android / Desktop:</b> Wähle im Browser-Menü „App installieren“ oder „Zum Startbildschirm hinzufügen“.</p><small>Web-Push braucht HTTPS und einen unterstützten Browser. Auf iPhone / iPad wird iOS / iPadOS 16.4 oder neuer benötigt. Sprachfunk braucht eine aktive Internetverbindung.</small></div>}
  </div>;
}
