import { useEffect, useRef, useState } from 'react';
import { Room, RoomEvent, Track, LocalAudioTrack, createLocalAudioTrack } from 'livekit-client';
import { MicOff, Radio as RadioIcon, Power, Waves } from 'lucide-react';
import { api } from './api';

export default function Radio({ tripId, active, endsAt }: { tripId: string; active: boolean; endsAt: number }) {
  const room = useRef<Room | null>(null);
  const track = useRef<LocalAudioTrack | null>(null);
  const context = useRef<AudioContext | null>(null);
  const audioElements = useRef(new Set<HTMLMediaElement>());
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
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
        setError('Das Mikrofon konnte nicht umgeschaltet werden. Bitte den Funk neu verbinden.');
      }
    }
  }
  async function disconnect() {
    generation.current++;
    track.current?.stop();
    track.current = null;
    sendingRef.current = false;
    await room.current?.disconnect();
    room.current = null;
    await context.current?.close();
    context.current = null;
    audioElements.current.forEach(el => el.remove());
    audioElements.current.clear();
    setConnected(false); setSending(false); setSpeakers([]);
  }
  async function connect() {
    if (busy) return;
    setBusy(true); setError('');
    const current = ++generation.current;
    const next = new Room({ audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      publishDefaults: { audioPreset: { maxBitrate: 32000 }, dtx: true, stopMicTrackOnMute: false } });
    room.current = next;
    let voiceHost = '';
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Mikrofonzugriff benötigt HTTPS und einen unterstützten Browser.');
      const credentials = await api(`/api/trips/${tripId}/voice-token`, 'POST');
      voiceHost = new URL(credentials.url).host;
      if (generation.current !== current) return;
      next.on(RoomEvent.TrackSubscribed, remote => {
        if (remote.kind === Track.Kind.Audio) { const el = remote.attach(); audioElements.current.add(el); document.body.appendChild(el); }
      });
      next.on(RoomEvent.TrackUnsubscribed, remote => remote.detach().forEach(el => { audioElements.current.delete(el); el.remove(); }));
      next.on(RoomEvent.ActiveSpeakersChanged, values => setSpeakers(values.map(p => p.name || 'Teilnehmer')));
      next.on(RoomEvent.Disconnected, () => {
        if (room.current !== next) return;
        setConnected(false); setSending(false); sendingRef.current = false;
        track.current?.stop(); track.current = null;
      });
      await next.connect(credentials.url, credentials.token);
      if (generation.current !== current) { await next.disconnect(); return; }
      await next.startAudio();
      const mic = await createLocalAudioTrack({ echoCancellation: true, noiseSuppression: true, autoGainControl: true });
      if (generation.current !== current) { mic.stop(); await next.disconnect(); return; }
      track.current = mic;
      mic.mediaStreamTrack.enabled = false;
      await next.localParticipant.publishTrack(mic, { source: Track.Source.Microphone });
      await mic.mute();
      setConnected(true);
    } catch (e) {
      const message = (e as Error).message || 'Die Sprachverbindung ist fehlgeschlagen.';
      setError(/signal connection|Load failed|Failed to fetch|NetworkError/i.test(message) && voiceHost
        ? `Sprachserver ${voiceHost} nicht erreichbar. Der Betreiber muss das HTTPS-Zertifikat, die öffentliche LiveKit-Adresse und den WebSocket-Router prüfen.`
        : message);
      await disconnect();
    }
    finally { setBusy(false); }
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
    return () => { clearInterval(interval); sourceTrack.stop(); source.disconnect(); void ctx.close(); context.current = null; };
  }, [connected, mode]);
  useEffect(() => {
    const mute = () => { if (modeRef.current === 'tap') void transmit(false); };
    window.addEventListener('blur', mute); document.addEventListener('visibilitychange', mute);
    const timer = window.setInterval(() => { if (Date.now() / 1000 >= endsAt) void disconnect(); }, 1000);
    return () => { clearInterval(timer); window.removeEventListener('blur', mute); document.removeEventListener('visibilitychange', mute); void disconnect(); };
  }, [tripId, endsAt]);
  useEffect(() => { if (!active) void disconnect(); }, [active]);
  return <section className="radio-panel">
    <div className="radio-title"><RadioIcon size={19} /><div><strong>Sprechfunk</strong><small>{connected ? 'Verbunden · mehrere Sprecher möglich' : 'Deine Gruppe auf einer Frequenz'}</small></div>
      <button className={`icon-button ${connected ? 'selected' : ''}`} aria-label={connected ? 'Funk trennen' : 'Funk verbinden'} disabled={!active || busy} onClick={() => void (connected ? disconnect() : connect())}><Power size={19} /></button>
    </div>
    <div className="segmented"><button className={mode === 'tap' ? 'selected' : ''} onClick={() => setMode('tap')}>Antippen</button><button className={mode === 'vox' ? 'selected' : ''} onClick={() => setMode('vox')}>Sprachaktivierung</button></div>
    <button className={`talk-button ${sending ? 'transmitting' : ''}`} disabled={!connected || mode !== 'tap'}
      aria-pressed={sending} aria-label={mode === 'vox' ? 'Sprachaktivierung aktiv' : sending ? 'Mikrofon ausschalten' : 'Mikrofon einschalten'}
      onClick={() => void transmit(!sendingRef.current)}
      onKeyDown={e => { if ((e.key === ' ' || e.key === 'Enter') && e.repeat) e.preventDefault(); }}>
      {sending ? <Waves size={27} /> : <MicOff size={27} />}<span>{mode === 'vox' ? 'Sprache wird automatisch erkannt' : sending ? 'Mikrofon an · Du sendest' : 'Mikrofon aus'}</span>
      {mode === 'tap' && <small>{sending ? 'Antippen zum Ausschalten' : 'Antippen zum Sprechen'}</small>}
    </button>
    <small className="radio-footer">{speakers.length ? speakers.join(', ') + ' spricht' : connected ? 'Bereit. Empfang läuft auch bei stummem Mikrofon.' : active ? 'Funk einschalten und Mikrofon freigeben.' : 'Funk ist nur im Fahrtzeitraum verfügbar.'}</small>
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}
