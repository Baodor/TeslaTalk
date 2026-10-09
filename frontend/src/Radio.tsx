import { t } from './i18n';
import { useEffect, useRef, useState } from 'react';
import { Room, RoomEvent, Track, LocalAudioTrack, createLocalAudioTrack } from 'livekit-client';
import { Mic, MicOff, Radio as RadioIcon, Power, Waves } from 'lucide-react';
import { api } from './api';

export default function Radio({ tripId, active, endsAt }: { tripId: string; active: boolean; endsAt: number }) {
  const room = useRef<Room | null>(null);
  const track = useRef<LocalAudioTrack | null>(null);
  const context = useRef<AudioContext | null>(null);
  const audioElements = useRef(new Set<HTMLMediaElement>());
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [phase, setPhase] = useState<'idle' | 'permission' | 'connecting' | 'ready' | 'reconnecting'>('idle');
  const [error, setError] = useState('');
  const [speakers, setSpeakers] = useState<string[]>([]);
  const [mode, setMode] = useState<'tap' | 'vox'>('tap');
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);
  const transmitQueue = useRef(Promise.resolve());
  const modeRef = useRef(mode);
  const generation = useRef(0);

  async function transmit(enabled: boolean) {
    const mic = track.current;
    if (!mic) return;
    sendingRef.current = enabled;
    // Apply rapid taps in order; a disconnected track must never update the UI.
    const operation = transmitQueue.current.then(async () => {
      if (track.current !== mic) return;
      await (enabled ? mic.unmute() : mic.mute());
      if (track.current === mic) setSending(enabled);
    });
    transmitQueue.current = operation.catch(() => {});
    try { await operation; }
    catch {
      if (track.current === mic) {
        mic.mediaStreamTrack.enabled = false;
        sendingRef.current = false; setSending(false);
        setError(t("Das Mikrofon konnte nicht umgeschaltet werden. Bitte den Funk neu verbinden."));
      }
    }
  }
  async function disconnect() {
    generation.current++;
    track.current?.stop();
    track.current = null;
    sendingRef.current = false;
    const previous = room.current;
    room.current = null;
    const previousContext = context.current;
    context.current = null;
    await previous?.disconnect();
    if (previousContext && previousContext.state !== 'closed') await previousContext.close().catch(() => {});
    audioElements.current.forEach(el => el.remove());
    audioElements.current.clear();
    setConnected(false); setSending(false); setSpeakers([]); setPhase('idle');
  }
  async function connect() {
    if (busyRef.current || !active || Date.now() / 1000 >= endsAt) return;
    busyRef.current = true; setBusy(true); setError(''); setPhase('permission');
    const current = ++generation.current;
    let voiceHost = '';
    let step = 'permission';
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error(t("Mikrofonzugriff benötigt HTTPS und einen unterstützten Browser."));
      // This invokes getUserMedia directly from the tap, before any network await.
      const mic = await createLocalAudioTrack({ echoCancellation: true, noiseSuppression: true, autoGainControl: true });
      if (generation.current !== current) { mic.stop(); return; }
      track.current = mic;
      mic.mediaStreamTrack.enabled = false;
      await mic.mute();
      if (generation.current !== current) { mic.stop(); return; }
      step = 'connecting'; setPhase('connecting');
      const credentials = await api(`/api/trips/${tripId}/voice-token`, 'POST');
      voiceHost = new URL(credentials.url).host;
      if (generation.current !== current) return;
      const next = new Room({ audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        publishDefaults: { audioPreset: { maxBitrate: 32000 }, dtx: true, stopMicTrackOnMute: false } });
      room.current = next;
      let established = false;
      next.on(RoomEvent.TrackSubscribed, remote => {
        if (remote.kind === Track.Kind.Audio) { const el = remote.attach(); audioElements.current.add(el); document.body.appendChild(el); }
      });
      next.on(RoomEvent.TrackUnsubscribed, remote => remote.detach().forEach(el => { audioElements.current.delete(el); el.remove(); }));
      next.on(RoomEvent.ActiveSpeakersChanged, values => setSpeakers(values.map(p => p.name || t("Teilnehmer"))));
      next.on(RoomEvent.Disconnected, () => {
        if (room.current !== next || !established) return;
        setError(t("Die Funkverbindung wurde getrennt. Bitte erneut verbinden."));
        void disconnect();
      });
      next.on(RoomEvent.Reconnecting, () => {
        if (room.current !== next) return;
        void transmit(false); setConnected(false); setPhase('reconnecting');
      });
      next.on(RoomEvent.Reconnected, () => {
        if (room.current !== next) return;
        setConnected(true); setPhase('ready');
      });
      await next.connect(credentials.url, credentials.token);
      if (generation.current !== current) { await next.disconnect(); return; }
      step = 'playback';
      await next.startAudio();
      if (generation.current !== current) { mic.stop(); await next.disconnect(); return; }
      step = 'publishing';
      await next.localParticipant.publishTrack(mic, { source: Track.Source.Microphone });
      if (generation.current !== current) { mic.stop(); await next.disconnect(); return; }
      established = true; setConnected(true); setPhase('ready');
    } catch (e) {
      if (generation.current !== current) return;
      const message = (e as Error).message || t("Die Sprachverbindung ist fehlgeschlagen.");
      const name = (e as Error).name;
      setError(step === 'permission' && /NotAllowedError|PermissionDeniedError/.test(name)
        ? t("Mikrofonzugriff wurde nicht erlaubt. Erlaube TeslaTalk den Mikrofonzugriff in den Website-Einstellungen deines Browsers und versuche es erneut.")
        : step === 'permission' && /NotFoundError|DevicesNotFoundError|NotReadableError/.test(name)
        ? t("Kein nutzbares Mikrofon gefunden. Prüfe dein Mikrofon und ob es von einer anderen Anwendung blockiert wird.")
        : /\bpc connection\b|\bICE\b|\bPeerConnection\b/i.test(message)
        ? t("Die Audioverbindung zu {0} ist gescheitert. Der Betreiber muss die direkten Audio-Ports, NAT und gegebenenfalls TURN prüfen.", {0: voiceHost || t("deinem Sprachserver")})
        : /signal connection|Load failed|Failed to fetch|NetworkError/i.test(message) && voiceHost
        ? t("Sprachserver {0} nicht erreichbar. Der Betreiber muss das HTTPS-Zertifikat, die öffentliche LiveKit-Adresse und den WebSocket-Router prüfen.", {0: voiceHost})
        : message);
      await disconnect();
    }
    finally { busyRef.current = false; setBusy(false); }
  }
  useEffect(() => { modeRef.current = mode; void transmit(false); }, [mode]);
  useEffect(() => {
    if (!connected || mode !== 'vox' || !track.current) return;
    // Analyze a clone so muting the outgoing track does not silence voice detection.
    const sourceTrack = track.current.mediaStreamTrack.clone();
    sourceTrack.enabled = true;
    const ctx = new AudioContext(); context.current = ctx;
    const source = ctx.createMediaStreamSource(new MediaStream([sourceTrack]));
    const analyser = ctx.createAnalyser(); analyser.fftSize = 512; source.connect(analyser);
    const values = new Float32Array(analyser.fftSize);
    let lastVoice = 0;
    let previous = false;
    const interval = window.setInterval(() => {
      analyser.getFloatTimeDomainData(values);
      const rms = Math.sqrt(values.reduce((sum, x) => sum + x * x, 0) / values.length);
      if (rms > 0.016) lastVoice = Date.now();
      const enabled = Date.now() - lastVoice < 500;
      if (enabled !== previous) { previous = enabled; void transmit(enabled); }
    }, 50);
    void ctx.resume();
    return () => {
      clearInterval(interval); sourceTrack.stop(); source.disconnect();
      if (ctx.state !== 'closed') void ctx.close().catch(() => {});
      if (context.current === ctx) context.current = null;
    };
  }, [connected, mode]);
  useEffect(() => {
    const mute = () => { if (modeRef.current === 'tap') void transmit(false); };
    window.addEventListener('blur', mute); document.addEventListener('visibilitychange', mute);
    const timer = window.setInterval(() => { if (Date.now() / 1000 >= endsAt) void disconnect(); }, 1000);
    return () => { clearInterval(timer); window.removeEventListener('blur', mute); document.removeEventListener('visibilitychange', mute); void disconnect(); };
  }, [tripId, endsAt]);
  useEffect(() => { if (!active) void disconnect(); }, [active]);
  const status = phase === 'permission' ? t("Mikrofonfreigabe wird angefragt")
    : phase === 'connecting' ? t("Funkverbindung wird aufgebaut")
    : phase === 'reconnecting' ? t("Verbindung wird wiederhergestellt")
    : !connected ? t("FUNK AUS") : sending ? t("DU SENDEST · MIKROFON AN")
    : mode === 'vox' ? t("FUNK AN · SPRACHERKENNUNG AN") : t("FUNK AN · MIKROFON AUS");
  return <section className={`radio-panel ${connected ? 'radio-connected' : ''} ${sending ? 'radio-sending' : ''}`}>
    <div className="radio-title"><RadioIcon size={19} /><div><strong>{t("Sprechfunk")}</strong><small>{connected ? t("Verbunden · mehrere Sprecher möglich") : t("Deine Gruppe auf einer Frequenz")}</small></div>
      <button className={`icon-button ${connected ? 'selected' : ''}`} aria-label={connected ? t("Funk trennen") : t("Funk verbinden")} aria-pressed={connected} disabled={!active || busy || phase === 'reconnecting'} onClick={() => void (connected ? disconnect() : connect())}><Power size={19} /></button>
    </div>
    <div className={`radio-status ${connected ? 'ready' : ''} ${sending ? 'sending' : ''}`} role="status" aria-live="polite"><span />{t(status)}</div>
    <div className="radio-permission">{connected ? <small>{t("Mikrofon freigegeben. Empfang läuft; Senden steuerst du unten.")}</small> : <button disabled={!active || busy || phase === 'reconnecting'} onClick={() => void connect()}><Mic size={18} />{busy ? t("Bitte warten …") : t("Mikrofon erlauben & Funk verbinden")}</button>}</div>
    <div className="segmented"><button className={mode === 'tap' ? 'selected' : ''} onClick={() => setMode('tap')}>{t("Antippen")}</button><button className={mode === 'vox' ? 'selected' : ''} onClick={() => setMode('vox')}>{t("Sprachaktivierung")}</button></div>
    <button className={`talk-button ${sending ? 'transmitting' : ''}`} disabled={!connected || mode !== 'tap'}
      aria-pressed={sending} aria-label={mode === 'vox' ? t("Sprachaktivierung aktiv") : sending ? t("Mikrofon ausschalten") : t("Mikrofon einschalten")}
      onClick={() => void transmit(!sendingRef.current)}
      onKeyDown={e => { if ((e.key === ' ' || e.key === 'Enter') && e.repeat) e.preventDefault(); }}>
      {sending ? <Waves size={32} /> : mode === 'vox' && connected ? <Mic size={32} /> : <MicOff size={32} />}<span>{sending ? t("Mikrofon an · Du sendest") : mode === 'vox' && connected ? t("Spracherkennung an · Wartet auf dich") : t("Mikrofon aus")}</span>
      {mode === 'tap' && <small>{sending ? t("Antippen zum Ausschalten") : t("Antippen zum Sprechen")}</small>}
    </button>
    <small className="radio-footer">{speakers.length ? speakers.join(', ') + t(" spricht") : connected ? t("Bereit. Empfang läuft auch bei stummem Mikrofon.") : active ? t("Funk einschalten und Mikrofon freigeben.") : t("Funk ist nur im Fahrtzeitraum verfügbar.")}</small>
    {error && <p className="error" role="alert">{t(error)}</p>}
  </section>;
}
