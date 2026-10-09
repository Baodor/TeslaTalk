import { t, getLocale, getLanguage, useLanguage } from './i18n';
import { useEffect, useRef, useState } from 'react';
import { Bell, BellOff, Download, RefreshCw, Send, X } from 'lucide-react';
import { api, ApiError } from './api';

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
  useLanguage();
  const language = getLanguage();
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null), [installed, setInstalled] = useState(standalone());
  const [help, setHelp] = useState(false), [enabled, setEnabled] = useState(false), [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false), [needsRepair, setNeedsRepair] = useState(false), [status, setStatus] = useState('');
  const busyRef = useRef(false), revision = useRef(0), retryRef = useRef<() => void>(() => {});
  const subscriptionRef = useRef<PushSubscription | null>(null);
  useEffect(() => {
    const before = (event: Event) => { event.preventDefault(); setPrompt(event as InstallPrompt); };
    const done = () => { setInstalled(true); setPrompt(null); };
    window.addEventListener('beforeinstallprompt', before); window.addEventListener('appinstalled', done);
    return () => { window.removeEventListener('beforeinstallprompt', before); window.removeEventListener('appinstalled', done); };
  }, []);
  useEffect(() => {
    revision.current++;
    subscriptionRef.current = null;
    setEnabled(Boolean(userId && preference(userId) === 'on')); setStatus(''); setNeedsRepair(false);
    if (!userId || !supported() || !config.push_ready) {
      if (userId) {
        setNeedsRepair(preference(userId) === 'on');
        setStatus(!supported() ? t("Dieser Browser unterstützt Web-Push hier nicht. Auf dem iPhone TeslaTalk über das Home-Bildschirm-Symbol öffnen.") : t("Der Betreiber muss Web-Push auf dem Server einrichten. Deine Auswahl bleibt gespeichert."));
      }
      setChecking(false); return;
    }
    let cancelled = false, syncing = false, lastAttempt = 0;
    async function sync(force = false) {
      if (cancelled || syncing || busyRef.current || (!force && Date.now() - lastAttempt < 60000)) return;
      syncing = true; lastAttempt = Date.now();
      const version = revision.current, languageAtStart = getLanguage();
      const current = () => !cancelled && version === revision.current;
      try {
        if (Notification.permission !== 'granted') {
          if (current()) {
            subscriptionRef.current = null;
            const wanted = preference(userId!) === 'on';
            setEnabled(wanted); setNeedsRepair(wanted);
            setStatus(Notification.permission === 'denied' ? t("Im Browser blockiert. Erlaube Benachrichtigungen in den Geräte- oder Browser-Einstellungen.") : t("Auf diesem Gerät noch nicht freigegeben."));
          }
          return;
        }
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.getSubscription();
        if (!current()) return;
        subscriptionRef.current = subscription;
        if (preference(userId!) === 'off') {
          subscriptionRef.current = null;
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
          setStatus(wanted ? t("Dein Browser-Abonnement fehlt. Aktiviere es erneut; deine Einstellung bleibt gespeichert.") : t("Benachrichtigungen sind auf diesem Gerät ausgeschaltet."));
          return;
        }
        // Browser permission and subscription establish local state before contacting
        // the server. An unavailable backend must not turn the setting off.
        remember(userId!, true); setEnabled(true); setNeedsRepair(false);
        await api('/api/push/subscribe', 'POST', { ...subscription.toJSON(), language: getLanguage() });
        if (current()) setStatus(t("Auf diesem Gerät aktiviert."));
      } catch {
        if (current()) setStatus(t("Der Serverabgleich steht aus. Deine Einstellung bleibt gespeichert; versuche es erneut, sobald die Verbindung steht."));
      } finally {
        syncing = false;
        if (current()) {
          setChecking(false);
          if (languageAtStart !== getLanguage()) queueMicrotask(() => void sync(true));
        }
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
  useEffect(() => { retryRef.current(); }, [language]);

  async function install() {
    if (prompt) { await prompt.prompt(); await prompt.userChoice; setPrompt(null); }
    else setHelp(true);
  }
  async function togglePush(disable = false) {
    if (!userId || busyRef.current) return;
    const turnOff = disable || (enabled && !needsRepair);
    if (!config.push_ready && !turnOff) { notify(t("Der Betreiber muss Web-Push in der Serverkonfiguration einrichten.")); return; }
    if (!supported()) {
      if (turnOff) { remember(userId, false); setEnabled(false); setNeedsRepair(false); }
      else setHelp(true);
      return;
    }
    const languageAtStart = getLanguage();
    busyRef.current = true; revision.current++; setBusy(true);
    try {
      if (!turnOff) {
        // Request permission directly from the tap, before asynchronous work.
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
          const wanted = preference(userId) === 'on';
          setEnabled(wanted); setNeedsRepair(wanted);
          setStatus(t("Nicht freigegeben. Erlaube Benachrichtigungen in den Geräte- oder Browser-Einstellungen."));
          return;
        }
      }
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (turnOff) {
        if (subscription && !await subscription.unsubscribe()) throw new Error(t("Das Browser-Abonnement konnte nicht deaktiviert werden. Bitte erneut versuchen."));
        subscriptionRef.current = null;
        remember(userId, false); setEnabled(false); setNeedsRepair(false); setStatus(t("Auf diesem Gerät ausgeschaltet."));
        if (subscription) await api('/api/push/unsubscribe', 'POST', { endpoint: subscription.endpoint });
        notify(t("Benachrichtigungen auf diesem Gerät deaktiviert."));
      } else {
        subscription ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: applicationKey(config.vapid_public_key) });
        subscriptionRef.current = subscription;
        remember(userId, true); setEnabled(true); setNeedsRepair(false);
        setStatus(t("Browser freigegeben. Serverabgleich läuft …"));
        await api('/api/push/subscribe', 'POST', { ...subscription.toJSON(), language: getLanguage() });
        setStatus(t("Auf diesem Gerät aktiviert."));
        notify(t("Benachrichtigungen für Nachrichten, Einladungen und Freundschaftsanfragen aktiviert."));
      }
    } catch (error) {
      setStatus(turnOff && preference(userId) === 'off' ? t("Im Browser ausgeschaltet. Der Serverabgleich ist fehlgeschlagen.") : t("Der Serverabgleich steht aus. Deine Einstellung bleibt gespeichert; versuche es erneut."));
      notify((error as Error).message || t("Benachrichtigungen konnten nicht eingerichtet werden."));
    } finally { busyRef.current = false; setBusy(false); setChecking(false); if (languageAtStart !== getLanguage()) retryRef.current(); }
  }
  async function sendTest() {
    if (busyRef.current || !supported() || !enabled || needsRepair) return;
    const languageAtStart = getLanguage();
    busyRef.current = true; revision.current++; setBusy(true);
    const subscription = subscriptionRef.current;
    try {
      if (!subscription || Notification.permission !== 'granted') {
        setNeedsRepair(true); setStatus(t("Das Browser-Abonnement fehlt oder die Freigabe wurde entzogen. Benachrichtigungen erneut aktivieren."));
        return;
      }
      // Start from the tap without another asynchronous browser lookup. Keep
      // this small request alive if the user closes the page to check the alert.
      const result = await api('/api/push/test', 'POST', { ...subscription.toJSON(), language: getLanguage() }, { keepalive: true });
      const acceptedAt = Number.isFinite(result.provider_accepted_at) ? new Date(result.provider_accepted_at * 1000).toLocaleTimeString(getLocale()) : '';
      const duration = Number.isFinite(result.provider_elapsed_ms) ? ` (${(result.provider_elapsed_ms / 1000).toFixed(2)} s)` : '';
      setStatus(t("Testnachricht an den Push-Dienst übergeben.{0} Prüfe die Mitteilungszentrale dieses Geräts.", {0: acceptedAt ? t(" Angenommen um {0}{1}.", {0: acceptedAt, 1: duration}) : ''}));
      notify(t("Testnachricht an dieses Gerät gesendet."));
    } catch (error) {
      if (error instanceof ApiError && error.status === 410) {
        subscriptionRef.current = null;
        await subscription?.unsubscribe().catch(() => {}); setNeedsRepair(true);
      }
      setStatus((error as Error).message || t("Die Testnachricht konnte nicht gesendet werden."));
      notify((error as Error).message);
    } finally { busyRef.current = false; setBusy(false); setChecking(false); if (languageAtStart !== getLanguage()) retryRef.current(); }
  }
  return { installed, help, setHelp, enabled, busy, checking, needsRepair, status, install, togglePush, sendTest, retry: () => retryRef.current() };
}
export type PWAState = ReturnType<typeof usePWAControls>;

export default function PWAControls({ controls }: { controls: PWAState }) {
  const { installed, help, setHelp, enabled, busy, checking, needsRepair, status, install, togglePush, sendTest, retry } = controls;
  return <section className="panel personal-notifications" aria-label={t("Benachrichtigungen und Web-App")}>
    <div className="panel-heading"><Bell size={21} /><h3>{t("Benachrichtigungen & Web-App")}</h3></div>
    <p>{t("Deine Einstellung gilt für dieses Gerät. Du erhältst Hinweise zu Nachrichten, Einladungen und Freundschaftsanfragen.")}</p>
    <div className="pwa-controls">
      <button onClick={() => void togglePush()} disabled={busy || checking} aria-pressed={enabled}>{enabled ? <Bell size={16} /> : <BellOff size={16} />}<span>{busy || checking ? t("Wird geprüft …") : needsRepair ? t("Benachrichtigungen erneut aktivieren") : enabled ? t("Benachrichtigungen an") : t("Benachrichtigungen")}</span></button>
      {needsRepair ? <button onClick={() => void togglePush(true)} disabled={busy}>{t("Deaktivieren")}</button> : enabled && <button onClick={retry} disabled={busy || checking}><RefreshCw size={16} />{t("Erneut abgleichen")}</button>}
      {enabled && !needsRepair && <button onClick={() => void sendTest()} disabled={busy || checking}><Send size={16} />{t("Testnachricht an dieses Gerät")}</button>}
      {!installed && <button onClick={() => void install()}><Download size={16} /><span>{t("Zum Home-Bildschirm")}</span></button>}
      {help && <div className="install-help" role="dialog" aria-label={t("TeslaTalk installieren")}><button className="icon-button" aria-label={t("Schließen")} onClick={() => setHelp(false)}><X size={18} /></button><img className="install-icon" src="/apple-touch-icon-v4.png" width="72" height="72" alt={t("Rotes TeslaTalk-Icon mit Walkie-Talkie und Tesla-T")} /><strong>{t("Dein Roadtrip auf dem Home-Bildschirm")}</strong><p><b>{t("iPhone / iPad:")}</b> {t(" Öffne die TeslaTalk-Startseite in Safari. Wähle Teilen → Zum Home-Bildschirm. Bei einem alten Buchstabensymbol den bisherigen Eintrag entfernen und neu hinzufügen. Starte TeslaTalk anschließend über das neue Symbol und aktiviere Benachrichtigungen.")}</p><p><b>{t("Android / Desktop:")}</b> {t(" Wähle im Browser-Menü „App installieren“ oder „Zum Startbildschirm hinzufügen“.")}</p><small>{t("Web-Push braucht HTTPS und einen unterstützten Browser. Auf iPhone / iPad wird iOS / iPadOS 16.4 oder neuer benötigt. Sprachfunk braucht eine aktive Internetverbindung.")}</small></div>}
    </div>
    <p className="notification-status hint" role="status">{t(status) || t("Auf diesem Gerät ausgeschaltet.")}</p>
    <small>{t("Ton und Vibration steuerst du in den Mitteilungseinstellungen deines Geräts. Ein Fokus kann Mitteilungen zurückhalten; eine geplante Übersicht zeigt sie erst später an.")}</small>
  </section>;
}
