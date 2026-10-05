import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react';
import { Radio as RadioIcon, Route, Users, Settings, LogOut, Plus, ArrowUpRight, ArrowLeft, Car, Battery, MapPin, Clock, MessageSquare, Send, X, Copy, QrCode, Images, Trophy, Shield, Check, KeyRound, Link as LinkIcon, RefreshCw, Navigation, CalendarDays, ChevronRight, UserPlus, Download, AlertCircle, SlidersHorizontal } from 'lucide-react';
import QRCode from 'qrcode';
import { api, ApiError, date, duration, localDate, type User, type Trip, type Participant } from './api';
import PWAControls, { usePWAControls, type PWAState } from './PWAControls';
import Avatar from './Avatar';
import { VehicleNavigation } from './NavigationPanel';
import RoutePlanning from './RoutePlanning';
import UsernameSetup from './UsernameSetup';
import AdminUsers from './AdminUsers';
import VehicleControls, { VehicleControlConsent } from './VehicleControls';
const TripMap = lazy(() => import('./TripMap'));
const Radio = lazy(() => import('./Radio'));
const ApiDocs = lazy(() => import('./ApiDocs'));

function Brand() { return <a className="brand" href="/" aria-label="TeslaTalk – Startseite"><img className="brand-symbol" src="/favicon.svg" alt="" /><span>Tesla<span className="accent">Talk</span><small>GEMEINSAM UNTERWEGS</small></span></a>; }
function Empty({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) { return <div className="empty-state">{icon}<h3>{title}</h3><p>{children}</p></div>; }
function CopyValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return <div className="copy-value"><code>{value}</code><button aria-label="Kopieren" onClick={() => void navigator.clipboard?.writeText(value).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); })}>{copied ? <Check size={17} /> : <Copy size={17} />}</button></div>;
}
function Modal({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} className="modal" onCancel={close}><header><h2>{title}</h2><button className="icon-button" aria-label="Schließen" onClick={close}><X size={21} /></button></header>{children}</dialog>;
}
function ActionForm({ children, onSubmit, label = 'Speichern' }: { children: ReactNode; onSubmit: (data: FormData) => Promise<void>; label?: string }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  return <form className="stack" onSubmit={async e => { e.preventDefault(); if (busy) return; const form = e.currentTarget; setBusy(true); setError(''); try { await onSubmit(new FormData(form)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}>
    {children}{error && <p className="error" role="alert">{error}</p>}<button className="primary" type="submit" disabled={busy}>{busy ? 'Wird gespeichert …' : label}<ArrowUpRight size={17} /></button>
  </form>;
}
function Field({ label, name, value = '', type = 'text', required = true, placeholder = '' }: { label: string; name: string; value?: string; type?: string; required?: boolean; placeholder?: string }) {
  return <label className="field"><span>{label}</span><input name={name} defaultValue={value} type={type} required={required} placeholder={placeholder} maxLength={type === 'text' ? 200 : undefined} /></label>;
}

export default function App() {
  const [config, setConfig] = useState<any>(null), [error, setError] = useState('');
  useEffect(() => { api('/api/config').then(setConfig).catch(e => setError(e.message)); }, []);
  if (!config) return <main className="center"><Brand /><p>{error || 'Verbinde mit deinem Server …'}</p>{error && <button onClick={() => location.reload()}>Erneut versuchen</button>}</main>;
  if (location.pathname.startsWith('/guest/')) return <GuestPage inviteKey={location.pathname.split('/')[2]} />;
  if (location.pathname.startsWith('/share/')) return <PublicPage shareKey={location.pathname.split('/')[2]} />;
  if (location.pathname === '/admin') return <AdminPage config={config} />;
  if (location.pathname === '/api-docs') return <Suspense fallback={<main className="center">API-Dokumentation wird geladen …</main>}><ApiDocs /></Suspense>;
  return <Dashboard config={config} />;
}

function Login({ config, reload }: { config: any; reload: () => void }) {
  return <main className="login-layout"><section className="login-story"><Brand /><div><span className="eyebrow">DEINE GRUPPE. DEINE FAHRT.</span><h1>Die Straße teilt sich.<br /><span>Die Verbindung bleibt.</span></h1><p>Sprechen, zusammenfinden und gemeinsam losfahren.<br />TeslaTalk hält deinen Roadtrip zusammen.</p><div className="login-features"><span><RadioIcon size={20} /> Sprechfunk</span><span><MapPin size={20} /> Live-Karte</span><span><Users size={20} /> Deine Freunde</span></div></div><footer>Selbst gehostet. Auf deinem Server.</footer></section>
    <section className="login-card"><span className="badge">TESLATALK · V0.1</span><h2>Bereit für die nächste Fahrt?</h2><p>Melde dich mit Tesla an und wähle dein Fahrzeug. Deine Zugangsdaten bleiben bei Tesla.</p>
      {config.tesla_ready ? <a className="button primary" href="/auth/tesla">Mit Tesla anmelden<ArrowUpRight size={19} /></a> : <div className="notice"><Settings size={20} /><span>Tesla-Anmeldung noch nicht eingerichtet.<small>Der Betreiber muss seine Fleet-API-Anwendung konfigurieren.</small></span></div>}
      {new URLSearchParams(location.search).has('error') && <p className="error">Tesla-Anmeldung wurde abgebrochen.</p>}
      {config.demo && <div className="demo-login"><span className="badge amber">DEMO · KEIN ECHTES FAHRZEUG</span><ActionForm label="Demo öffnen" onSubmit={async data => { await api('/api/demo/login', 'POST', { query: data.get('name') }); reload(); }}><Field label="Dein Demo-Name" name="name" value="Roadtrip-Fahrer" /></ActionForm></div>}
      <small>Mitfahrer? Scanne den QR-Code deiner Fahrt und nutze deinen persönlichen PIN.</small><a className="text-link" href="/admin"><Shield size={14} /> Administration</a>
    </section></main>;
}

function Dashboard({ config }: { config: any }) {
  const [user, setUser] = useState<User | null>(null), [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [trips, setTrips] = useState<Trip[]>([]), [vehicles, setVehicles] = useState<any[]>([]), [invites, setInvites] = useState<Trip[]>([]);
  const [view, setView] = useState('trips'), [selected, setSelected] = useState<string | null>(location.pathname.startsWith('/trip/') ? location.pathname.split('/')[2] : null);
  const [modal, setModal] = useState<'create' | 'join' | null>(null), [notice, setNotice] = useState('');
  const pwa = usePWAControls(config, user?.id, setNotice);
  async function load() {
    setLoadError('');
    try {
      const me = await api<User>('/api/me'); setUser(me);
      if (me.needs_username) { setTrips([]); setInvites([]); setVehicles([]); return; }
      const [list, incoming, cars] = await Promise.allSettled([
        api<Trip[]>('/api/trips'), api<Trip[]>('/api/invites'),
        me.provider === 'guest' ? Promise.resolve([]) : api<any[]>('/api/vehicles'),
      ]);
      if (list.status === 'fulfilled') setTrips(list.value);
      if (incoming.status === 'fulfilled') setInvites(incoming.value);
      if (cars.status === 'fulfilled') setVehicles(cars.value);
      const failed = [list, incoming, cars].find(result => result.status === 'rejected');
      if (failed?.status === 'rejected') setNotice('Ein Teil deiner Daten konnte nicht geladen werden. ' + (failed.reason?.message || 'Bitte erneut versuchen.'));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) setUser(null);
      else if (user) setNotice((error as Error).message || 'Verbindung fehlgeschlagen.');
      else setLoadError((error as Error).message || 'Verbindung fehlgeschlagen.');
    } finally { setLoaded(true); }
  }
  useEffect(() => { void load(); }, []);
  useEffect(() => { if (notice) { const timer = setTimeout(() => setNotice(''), 8000); return () => clearTimeout(timer); } }, [notice]);
  function openTrip(id: string) { setSelected(id); setView('trips'); history.replaceState({}, '', '/trip/' + id); }
  function goHome(next = 'trips') { setSelected(null); setView(next); history.replaceState({}, '', '/'); }
  if (!loaded) return <main className="center"><Brand /><p>Deine Fahrten werden geladen …</p></main>;
  if (!user && loadError) return <main className="center"><Brand /><p role="alert">{loadError}</p><button onClick={() => void load()}>Erneut versuchen</button></main>;
  if (!user) return <Login config={config} reload={() => void load()} />;
  if (user.needs_username) return <UsernameSetup user={user} complete={account => { setUser(account); void load(); }} />;
  const guest = user.provider === 'guest';
  return <div className="app-shell"><aside className="sidebar"><Brand /><div className="sidebar-label">DEIN ROADTRIP</div><nav>
    <button className={view === 'trips' ? 'active' : ''} onClick={() => goHome()}><Route size={20} /> Fahrten</button>
    {!guest && <><button className={view === 'friends' ? 'active' : ''} onClick={() => goHome('friends')}><Users size={20} /> Freunde</button></>}<button className={view === 'settings' ? 'active' : ''} onClick={() => goHome('settings')}><Settings size={20} /> Mein Profil</button>
  </nav><div className="sidebar-bottom"><div className="server-pill"><span className="status-dot" /> {config.demo ? 'Demo-Server' : 'Privater Server'}</div><div className="user-block"><Avatar name={user.display_name} url={user.avatar_url} /><div><strong>{user.display_name}</strong><small>{guest ? 'Mitfahrer · Zugang auf Zeit' : '@' + user.username}</small></div><button className="icon-button" aria-label="Abmelden" onClick={() => void api('/auth/logout', 'POST').then(() => location.assign('/'))}><LogOut size={18} /></button></div></div></aside>
    <main className="main-content"><div className="utility-bar"><button className="mobile-logout icon-button" aria-label="Abmelden" onClick={() => void api('/auth/logout', 'POST').then(() => location.assign('/'))}><LogOut size={18} /></button></div>{config.demo && <div className="demo-bar">DEMO-MODUS · Fahrzeugwerte sind Beispieldaten</div>}
      {notice && <div className="toast" role="status"><AlertCircle size={18} />{notice}<button aria-label="Hinweis schließen" onClick={() => setNotice('')}><X size={16} /></button></div>}
      <Suspense fallback={<p className="hint">Fahrt wird geladen …</p>}>{selected ? <TripPage key={selected} tripId={selected} user={user} vehicles={vehicles} back={() => goHome()} reload={() => void load()} notify={setNotice} /> : view === 'friends' ? <Friends notify={setNotice} /> : view === 'settings' ? <ProfilePage user={user} vehicles={vehicles} reload={load} notify={setNotice} pwa={pwa} teslaReady={config.tesla_ready} guestTripId={trips[0]?.id} /> : <>
        <header className="page-header"><div><span className="eyebrow">GEMEINSAM WEITER</span><h1>Deine Fahrten<span className="accent">.</span></h1><p>Ein Ziel. Deine Leute. Alles an einem Ort.</p></div>{!guest && <div className="header-actions"><button onClick={() => setModal('join')}>Mit PIN beitreten</button><button className="primary" onClick={() => setModal('create')}><Plus size={18} /> Fahrt erstellen</button></div>}</header>
        {!guest && !vehicles.length && <div className="notice"><Car size={24} /><span>Verbinde zuerst dein Fahrzeug.<small>Öffne dein Profil und rufe deine Tesla-Fahrzeuge ab.</small></span><button onClick={() => goHome('settings')}>Zum Profil<ChevronRight size={17} /></button></div>}
        {invites.length > 0 && <section className="panel"><h3>Du bist eingeladen</h3>{invites.map(trip => <div className="list-row" key={trip.id}><div><strong>{trip.title}</strong><small>{date(trip.starts_at)}</small></div><button className="primary" onClick={() => void api(`/api/trips/${trip.id}/accept`, 'POST').then(() => { void load(); openTrip(trip.id); }).catch(e => setNotice(e.message))}>Mitfahren</button></div>)}</section>}
        <div className="summary-strip"><div><Route size={20} /><strong>{trips.filter(t => t.status !== 'finished').length}</strong><span>Geplante & aktive Fahrten</span></div><div><Car size={20} /><strong>{vehicles.length}</strong><span>Deine Fahrzeuge</span></div><div><Shield size={20} /><span>Standorte bleiben<br /><strong>in deiner Gruppe</strong></span></div></div>
        {trips.length ? <div className="trip-grid">{trips.map(trip => <button className="trip-card" key={trip.id} onClick={() => openTrip(trip.id)}><div className="trip-card-top"><span className={`badge ${trip.status === 'active' ? 'accent-badge' : ''}`}>{trip.status === 'active' ? '● UNTERWEGS' : trip.status === 'planned' ? 'GEPLANT' : 'ABGESCHLOSSEN'}</span><ArrowUpRight size={20} /></div><div className="trip-card-icon"><Route size={31} /></div><h2>{trip.title}</h2><p><MapPin size={15} />{trip.destination || 'Das Ziel ist die gemeinsame Fahrt'}</p><footer><span><CalendarDays size={15} />{new Date(trip.starts_at * 1000).toLocaleDateString('de-DE')}</span><span><Users size={15} />{trip.participants}</span></footer></button>)}</div> : <Empty icon={<Route size={43} />} title="Die nächste Fahrt wartet auf dich.">Erstelle einen Roadtrip oder tritt mit dem PIN deiner Freunde bei.</Empty>}
        <div className="roadmap-teaser"><WavesGraphic /><div><span className="eyebrow">ALS NÄCHSTES</span><h3>Zusammen laden. Erinnerungen teilen.</h3><p>Gemeinsame Ladeplanung, Immich-Alben und der „Ich muss aufs Klo“-Knopf stehen auf der Roadmap.</p></div><a href="https://github.com/Baodor/TeslaTalk#roadmap" target="_blank" rel="noreferrer">Roadmap<ArrowUpRight size={17} /></a></div>
      </>}</Suspense>
    </main>
    {modal === 'create' && <CreateTrip close={() => setModal(null)} created={id => { setModal(null); void load(); openTrip(id); }} />}
    {modal === 'join' && <Modal title="Mit PIN beitreten" close={() => setModal(null)}><p>Du brauchst den sechsstelligen Fahrer-PIN der Fahrt.</p><ActionForm label="Fahrt beitreten" onSubmit={async data => { const trip = await api('/api/trips/join', 'POST', { pin: data.get('pin') }); setModal(null); void load(); openTrip(trip.id); }}><Field label="Fahrer-PIN" name="pin" placeholder="000000" /></ActionForm></Modal>}
  </div>;
}

function WavesGraphic() { return <div className="waves-graphic"><RadioIcon size={40} /></div>; }
function CreateTrip({ close, created }: { close: () => void; created: (id: string) => void }) {
  const [result, setResult] = useState<any>(null);
  return <Modal title={result ? 'Deine Fahrt steht.' : 'Neue Fahrt erstellen'} close={close}>{result ? <div className="stack"><p>Teile diesen Fahrer-PIN mit deinen Freunden. Er wird nur jetzt angezeigt.</p><CopyValue value={result.pin} /><button className="primary" onClick={() => created(result.id)}>Fahrt öffnen<ArrowUpRight size={18} /></button></div> : <ActionForm label="Fahrt erstellen" onSubmit={async data => setResult(await api('/api/trips', 'POST', { title: data.get('title'), destination: data.get('destination'), starts_at: new Date(String(data.get('start'))).toISOString(), ends_at: new Date(String(data.get('end'))).toISOString() }))}>
    <Field label="Name der Fahrt" name="title" placeholder="Ein Wochenende am Meer" /><Field label="Ziel" name="destination" required={false} placeholder="Wohin geht es?" /><div className="two-fields"><Field label="Von" name="start" type="datetime-local" value={localDate(new Date())} /><Field label="Bis" name="end" type="datetime-local" value={localDate(new Date(Date.now() + 8 * 3600000))} /></div><p className="hint">Mitfahrerzugänge gelten genau in diesem Zeitraum. Nach Fahrtende ist der Chat nur noch lesbar.</p>
  </ActionForm>}</Modal>;
}

function TripPage({ tripId, user, vehicles, back, reload, notify }: { tripId: string; user: User; vehicles: any[]; back: () => void; reload: () => void; notify: (value: string) => void }) {
  const [trip, setTrip] = useState<any>(null), [error, setError] = useState(''), [tab, setTab] = useState('map');
  const [messages, setMessages] = useState<any[]>([]), [text, setText] = useState(''), [sending, setSending] = useState(false);
  const [connected, setConnected] = useState(false), [gps, setGps] = useState(false), [invite, setInvite] = useState(false);
  const [qr, setQr] = useState(''), [rank, setRank] = useState<any[]>([]), [traces, setTraces] = useState<any[]>([]);
  const [friends, setFriends] = useState<any[]>([]), [rankBy, setRankBy] = useState('consumption_kwh_100km');
  const messageEnd = useRef<HTMLDivElement>(null);
  const leader = trip?.leader_id === user.id;
  const active = trip?.status === 'active';
  useEffect(() => { if (tab === 'controls' && !leader) setTab('map'); }, [tab, leader]);
  async function refresh() { try { setTrip(await api(`/api/trips/${tripId}`)); } catch (e) { setError((e as Error).message); } }
  function addMessage(message: any) { setMessages(previous => previous.some(item => item.id === message.id) ? previous : [...previous, message].slice(-500)); }
  useEffect(() => {
    let stopped = false, socket: WebSocket | null = null, timer = 0;
    void Promise.all([api(`/api/trips/${tripId}`), api(`/api/trips/${tripId}/messages`)]).then(([detail, chat]) => { if (!stopped) { setTrip(detail); setMessages(chat); } }).catch(e => { if (!stopped) setError(e.message); });
    const connect = () => {
      if (stopped) return;
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/ws/trips/${tripId}`);
      socket.onopen = () => setConnected(true);
      socket.onmessage = event => {
        const data = JSON.parse(event.data);
        if (data.type === 'participants') setTrip((current: any) => current ? { ...current, participants_detail: data.participants } : current);
        if (data.type === 'message') addMessage(data.message);
        if (data.type === 'navigation') setTrip((current: any) => current ? { ...current, navigation: data.navigation, ...(data.route_overview ? {route_overview:data.route_overview} : {}) } : current);
        if (data.type === 'controls') setTrip((current:any)=>current?{...current,vehicle_controls:data.vehicle_controls}:current);
        if (data.type === 'ended') { void refresh(); setGps(false); }
      };
      socket.onclose = () => { setConnected(false); if (!stopped) timer = window.setTimeout(connect, 5000); };
    };
    connect();
    const clock = window.setInterval(() => { void refresh(); }, 30000);
    return () => { stopped = true; clearTimeout(timer); clearInterval(clock); socket?.close(); };
  }, [tripId]);
  useEffect(() => { messageEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [messages.length, tab]);
  useEffect(() => { if (trip?.guest_url) void QRCode.toDataURL(trip.guest_url, { width: 240, margin: 2, color: { dark: '#101a20', light: '#ffffff' } }).then(setQr); }, [trip?.guest_url]);
  useEffect(() => {
    if (!gps || !active) return;
    if (!navigator.geolocation) { notify('Dieser Browser unterstützt keine Standortfreigabe.'); setGps(false); return; }
    let last = 0, stopped = false;
    let uploading = Promise.resolve();
    const watch = navigator.geolocation.watchPosition(position => {
      if (stopped || Date.now() - last < 10000) return;
      last = Date.now();
      uploading = uploading.then(() => api(`/api/trips/${tripId}/samples`, 'POST', { latitude: position.coords.latitude, longitude: position.coords.longitude,
        speed_kmh: position.coords.speed === null ? null : Math.max(0, position.coords.speed * 3.6), heading: position.coords.heading, source: 'browser' })).catch(e => { if (!stopped) notify(e.message); });
    }, e => { notify('Standortfreigabe: ' + e.message); setGps(false); }, { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 });
    return () => {
      stopped = true; navigator.geolocation.clearWatch(watch);
      // Remove only the live person marker. Recorded trip history stays separate.
      void uploading.then(() => api(`/api/trips/${tripId}/location`, 'DELETE')).catch(() => {});
    };
  }, [gps, active, tripId]);
  useEffect(() => { if (tab === 'history') void Promise.all([api(`/api/trips/${tripId}/ranking`), api(`/api/trips/${tripId}/history`)]).then(([r, t]) => { setRank(r); setTraces(t); }).catch(e => notify(e.message)); }, [tab, tripId]);
  useEffect(() => { if (invite) void api<any[]>('/api/friends').then(rows => setFriends(rows.filter(row => row.status === 'accepted'))).catch(e => notify(e.message)); }, [invite]);
  async function send() {
    if (!text.trim() || sending) return;
    setSending(true);
    try { addMessage(await api(`/api/trips/${tripId}/messages`, 'POST', { text })); setText(''); } catch (e) { notify((e as Error).message); } finally { setSending(false); }
  }
  if (error) return <><button onClick={back}><ArrowLeft size={16} />Zurück</button><Empty icon={<AlertCircle size={38} />} title="Fahrt nicht verfügbar">{error}</Empty></>;
  if (!trip) return <div className="center">Fahrt wird geladen …</div>;
  const participants: Participant[] = trip.participants_detail;
  const mine = vehicles.find(v => v.id === user.favorite_vehicle);
  const ranked = [...rank].sort((a, b) => a[rankBy] == null ? 1 : b[rankBy] == null ? -1 : rankBy === 'average_speed_kmh' ? b[rankBy] - a[rankBy] : a[rankBy] - b[rankBy]);
  return <div className="trip-page"><header className="page-header compact"><div><button className="back-button" onClick={back}><ArrowLeft size={16} /> Alle Fahrten</button><h1>{trip.title}</h1><p><MapPin size={15} />{trip.destination || 'Gemeinsam unterwegs'}<span>·</span>{date(trip.starts_at)} – {date(trip.ends_at)}</p></div><div className="header-actions"><span className={`badge ${active ? 'accent-badge' : ''}`}>{active ? '● UNTERWEGS' : trip.status === 'planned' ? 'GEPLANT' : 'ABGESCHLOSSEN'}</span>{leader && trip.status !== 'finished' && <button onClick={() => setInvite(true)}><UserPlus size={17} />Einladen</button>}</div></header>
    <div className="trip-tabs">{[['map', MapPin, 'Karte'], ['chat', MessageSquare, 'Chat'], ['photos', Images, 'Fotos & Mitfahrer'], ['history', Trophy, 'Verlauf'], ...(leader ? [['controls', SlidersHorizontal, 'Fahrzeugsteuerung']] : [])].map(([id, Icon, label]) => { const I = Icon as typeof MapPin; return <button key={String(id)} className={tab === id ? 'active' : ''} onClick={() => setTab(String(id))}><I size={18} />{String(label)}</button>; })}<span className="socket-state"><span className={`status-dot ${connected ? '' : 'offline'}`} />{connected ? 'Live verbunden' : 'Verbindung wird aufgebaut'}</span></div>
    <div className="trip-workspace"><section className="trip-stage">
      {leader && <div hidden={tab !== 'controls'}><VehicleControls tripId={tripId} userId={user.id} leader={leader} active={active} driver={trip.my_role==='driver'&&user.provider!=='guest'} overview={trip.vehicle_controls} update={value=>setTrip((current:any)=>({...current,vehicle_controls:value}))}/></div>}
      {tab === 'map' && !leader && trip.my_role === 'driver' && user.provider !== 'guest' && active && <section className="panel"><div className="panel-heading"><Car size={21}/><h3>Freigabe meines Fahrzeugs</h3></div><VehicleControlConsent tripId={tripId} userId={user.id} active={active} driver overview={trip.vehicle_controls} update={value=>setTrip((current:any)=>({...current,vehicle_controls:value}))}/></section>}
      {tab === 'map' && <RoutePlanning tripId={tripId} userId={user.id} leader={leader} active={active} finished={trip.status === 'finished'} destination={trip.destination} navigation={trip.navigation || null} overview={trip.route_overview}
        update={(navigation, overview) => setTrip((current: any) => ({...current,...(navigation !== undefined ? {navigation} : {}),...(overview ? {route_overview:overview} : {})}))} />}
      {tab === 'map' && <><TripMap participants={participants} navigation={trip.navigation || null} /><div className="map-actions"><span><Shield size={16} />Standorte sind nur in dieser Fahrt sichtbar.</span>{active && <button aria-pressed={gps} className={gps ? 'selected' : ''} onClick={() => setGps(!gps)}><Navigation size={17} />{gps ? 'Standortfreigabe stoppen' : 'Standort teilen'}</button>}{mine && <button onClick={() => void api(`/api/vehicles/${encodeURIComponent(mine.id)}/refresh`, 'POST').then(() => { void refresh(); notify('Fahrzeugdaten aktualisiert.'); }).catch(e => notify(e.message))}><RefreshCw size={17} />Daten abrufen</button>}</div></>}
      {tab === 'chat' && <section className="chat-panel"><div className="panel-heading"><MessageSquare size={20} /><h3>Fahrt-Chat</h3><span className="badge">{participants.length} TEILNEHMER</span></div><div className="message-list">{messages.length ? messages.map(message => <div className={`message ${message.user_id === user.id ? 'own' : ''}`} key={message.id}><div><strong>{message.display_name}</strong><time>{new Date(message.created_at * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}</time></div><p>{message.text}</p></div>) : <Empty icon={<MessageSquare size={30} />} title="Sag deiner Gruppe Hallo.">Nachrichten bleiben bei dieser Fahrt gespeichert.</Empty>}<div ref={messageEnd} /></div><form className="chat-input" onSubmit={e => { e.preventDefault(); void send(); }}><input aria-label="Nachricht" placeholder={trip.status === 'finished' ? 'Fahrt beendet · Chat ist nur lesbar' : 'Nachricht an deine Fahrt …'} value={text} maxLength={2000} onChange={e => setText(e.target.value)} disabled={trip.status === 'finished'} /><button className="primary" aria-label="Nachricht senden" disabled={!text.trim() || sending || trip.status === 'finished'}><Send size={20} /></button></form></section>}
      {tab === 'photos' && <section className="panel photos-panel"><div className="panel-heading"><Images size={21} /><h3>Fotos & Mitfahrer</h3><span className="badge amber">IMMICH FOLGT</span></div><p>Geplantes Album: <strong>{trip.album.name}</strong>. Die Immich-Anbindung und Foto-Uploads kommen im nächsten Schritt.</p>{leader && <div className="guest-layout"><div className="qr-card">{qr && <img src={qr} alt="QR-Code für die Mitfahrer-Selbstregistrierung" />}<strong>Mitfahrer selbst registrieren</strong><small>QR scannen · eigenen Namen und PIN wählen · kein Tesla-Konto</small><CopyValue value={trip.guest_url} /></div><div className="stack"><h3>Registrierte Mitfahrer</h3><p>Jeder Mitfahrer registriert sich über den QR-Link selbst. Du musst Namen und PINs nicht vorab anlegen.</p>{participants.filter(p => p.role === 'passenger').map(p => <div className="list-row" key={p.id}><span>{p.display_name}</span><span className="badge">BEIGETRETEN</span></div>)}{!participants.some(p => p.role === 'passenger') && <p className="hint">Noch keine Mitfahrer registriert.</p>}</div></div>}<div className="notice"><Clock size={20} /><span>Mitfahrerzugänge enden am {date(trip.finished_at || trip.ends_at)}.<small>Immich und Foto-Uploads sind noch nicht angebunden.</small></span></div>{leader && trip.status === 'finished' && <div className="stack"><h3>Fahrt öffentlich teilen</h3><p>Ein separater Leselink zeigt die Fahrtübersicht. Private Chats, Kennzeichen und GPS-Verläufe bleiben intern.</p>{trip.share_url && <CopyValue value={trip.share_url} />}<div className="header-actions"><button onClick={() => void api(`/api/trips/${tripId}/share`, 'POST').then(refresh).catch(e => notify(e.message))}><LinkIcon size={16} />Leselink {trip.share_url ? 'erneuern' : 'erstellen'}</button>{trip.share_url && <button onClick={() => void api(`/api/trips/${tripId}/share`, 'DELETE').then(refresh).catch(e => notify(e.message))}>Freigabe widerrufen</button>}</div></div>}</section>}
      {tab === 'history' && <section className="panel"><div className="panel-heading"><Trophy size={21} /><h3>Aufgezeichnete Fahrt</h3><a className="button" href={`/api/trips/${tripId}/export`}><Download size={16} />Daten exportieren</a></div><p>Verbrauch wird aus gemessenen Energie- und Kilometerzählern berechnet. Ohne Energiedaten erscheint kein erfundener Verbrauchswert.</p><div className="segmented ranking-sort">{[['consumption_kwh_100km', 'Niedrigster Verbrauch'], ['duration_seconds', 'Kürzeste Zeit'], ['average_speed_kmh', 'Ø Tempo']].map(([key, label]) => <button key={key} className={rankBy === key ? 'selected' : ''} onClick={() => setRankBy(key)}>{label}</button>)}</div><div className="table-scroll"><table><thead><tr><th>Teilnehmer</th><th>Verbrauch</th><th>Strecke</th><th>Zeit</th><th>Ø Tempo</th></tr></thead><tbody>{ranked.map(row => <tr key={row.user_id}><td>{participants.find(p => p.id === row.user_id)?.display_name || 'Teilnehmer'}</td><td>{row.consumption_kwh_100km === null ? '—' : row.consumption_kwh_100km + ' kWh/100 km'}</td><td>{row.distance_km === null ? '—' : row.distance_km + ' km'}</td><td>{duration(row.duration_seconds)}</td><td>{row.average_speed_kmh === null ? '—' : row.average_speed_kmh + ' km/h'}</td></tr>)}</tbody></table></div>{!rank.length && <p className="hint">Noch keine Messwerte aufgezeichnet.</p>}<TripMap participants={participants} traces={traces} /><small>Die Karte zeigt bis zu 1.000 Messpunkte. Der Export enthält die vollständige Aufzeichnung. Zeit und Tempo beziehen sich auf die erfassten Abschnitte.</small></section>}
    </section><aside className="trip-side"><section className="panel participants-panel"><div className="panel-heading"><Users size={20} /><h3>Deine Gruppe</h3><span className="count">{participants.length}</span></div>{participants.map(p => <div className="participant" key={p.id}><Avatar name={p.display_name} url={p.avatar_url} className={p.online ? 'online' : ''} /><div className="participant-info"><strong>{p.display_name}{p.id === trip.leader_id && <span className="leader-label">Leitung</span>}</strong><small>{p.role === 'passenger' ? 'Mitfahrer' : [p.model, p.plate].filter(Boolean).join(' · ')}</small><span className="vehicle-stats">{p.data.battery_pct != null && <span><Battery size={14} />{p.data.battery_pct} %</span>}{p.data.range_km != null && <span>{p.data.range_km} km</span>}</span></div></div>)}</section><Radio tripId={tripId} active={active} endsAt={trip.finished_at || trip.ends_at} />{leader && trip.status !== 'finished' && <button className="finish-button" onClick={() => { if (window.confirm('Fahrt jetzt beenden? Mitfahrerzugänge und Sprachfunk werden geschlossen.')) void api(`/api/trips/${tripId}/finish`, 'POST').then(() => { void refresh(); reload(); }).catch(e => notify(e.message)); }}>Fahrt jetzt beenden</button>}</aside></div>
    {invite && <Modal title="Freunde einladen" close={() => setInvite(false)}><p>Fahrer benötigen ein TeslaTalk-Konto. Für Mitfahrer ohne Tesla-Konto nutzt du „Fotos & Mitfahrer“.</p>{friends.length > 0 && <div className="stack friend-picker">{friends.map(friend => <button key={friend.user.id} onClick={() => void api(`/api/trips/${tripId}/invite`, 'POST', { query: friend.user.username }).then(() => { notify(friend.user.display_name + ' ist eingeladen.'); setInvite(false); }).catch(e => notify(e.message))}><UserPlus size={17} />{friend.user.display_name}<small>@{friend.user.username}</small></button>)}</div>}<ActionForm label="Einladung senden" onSubmit={async data => { await api(`/api/trips/${tripId}/invite`, 'POST', { query: data.get('query') }); notify('Einladung ist im Konto des Fahrers verfügbar.'); setInvite(false); }}><Field label="Benutzername, Kennzeichen oder E-Mail" name="query" /></ActionForm></Modal>}
  </div>;
}

function Friends({ notify }: { notify: (value: string) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const load = () => api('/api/friends').then(setRows).catch(e => notify(e.message));
  useEffect(() => { void load(); }, []);
  return <><header className="page-header"><div><span className="eyebrow">DEINE LEUTE</span><h1>Freunde<span className="accent">.</span></h1><p>Einmal verbinden. Beim nächsten Roadtrip leichter zusammenfinden.</p></div></header><div className="settings-grid"><section className="panel"><h3>Freund hinzufügen</h3><p>Suche ein bereits registriertes Fahrer-Konto.</p><ActionForm label="Freundschaft anfragen" onSubmit={async data => { await api('/api/friends', 'POST', { query: data.get('query') }); await load(); notify('Freundschaft angefragt.'); }}><Field label="Benutzername, Kennzeichen oder E-Mail" name="query" placeholder="Exakte Angabe" /></ActionForm></section><section className="panel"><h3>Deine Verbindungen</h3>{rows.length ? rows.map(row => <div className="list-row" key={row.user.id}><Avatar name={row.user.display_name} url={row.user.avatar_url} /><div className="grow"><strong>{row.user.display_name}</strong><small>@{row.user.username} · {row.status === 'accepted' ? 'Befreundet' : row.incoming ? 'Möchte sich verbinden' : 'Anfrage gesendet'}</small></div>{row.status === 'pending' && row.incoming && <button className="primary" onClick={() => void api(`/api/friends/${row.user.id}/accept`, 'POST').then(load).catch(e => notify(e.message))}><Check size={17} />Annehmen</button>}<button className="icon-button" aria-label="Verbindung entfernen" onClick={() => void api(`/api/friends/${row.user.id}`, 'DELETE').then(load).catch(e => notify(e.message))}><X size={17} /></button></div>) : <Empty icon={<Users size={34} />} title="Deine Gruppe beginnt hier.">Frage deine Freunde nach ihrem Benutzernamen.</Empty>}</section></div></>;
}

function ProfilePage({ user, vehicles, reload, notify, pwa, teslaReady, guestTripId }: { user: User; vehicles: any[]; reload: () => Promise<void>; notify: (value: string) => void; pwa: PWAState; teslaReady: boolean; guestTripId?: string }) {
  const [keys, setKeys] = useState<any[]>([]), [newKey, setNewKey] = useState(''), [unlimited, setUnlimited] = useState(false);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const guest = user.provider === 'guest';
  const loadKeys = () => api('/api/keys').then(setKeys).catch(e => notify(e.message));
  useEffect(() => { if (!guest) void loadKeys(); }, []);
  async function refreshAvatar() {
    if (avatarBusy) return;
    setAvatarBusy(true);
    try {
      const profile = await api<User>('/api/me/tesla-profile', 'POST');
      await reload(); notify(profile.avatar_url ? 'Tesla-Profilbild aktualisiert.' : 'Tesla liefert für dieses Konto derzeit kein Profilbild.');
    } catch (error) { notify((error as Error).message); }
    finally { setAvatarBusy(false); }
  }
  return <>
    <header className="page-header"><div><span className="eyebrow">DEIN PROFIL</span><h1>Startklar<span className="accent">.</span></h1><p>{guest ? 'Deine persönlichen Einstellungen für diese Fahrt.' : 'Dein Name für die Gruppe. Dein Fahrzeug für die Fahrt.'}</p></div></header>
    <div className="settings-grid">
      <PWAControls controls={pwa} />
      {guest && <section className="panel" aria-label="Tesla-Profil für Mitfahrer">
        <h3>Dein Tesla-Profil als Mitfahrer</h3>
        <div className="profile-identity"><Avatar name={user.display_name} url={user.avatar_url} className="profile-avatar" /><div><strong>{user.display_name}</strong><small>{user.tesla_profile_linked ? 'Tesla-Profil verknüpft · Mitfahrer' : 'Mitfahrer mit eigenem Namen und PIN'}</small></div></div>
        <p>Verknüpfe dein Tesla-Konto für dein Profilbild. Du bleibst Mitfahrer; dein Auto wird weder abgerufen noch in Reichweite, Akku oder Routenplanung einbezogen.</p>
        {teslaReady && guestTripId ? <a className="button primary" href={'/auth/tesla/passenger?trip_id='+encodeURIComponent(guestTripId)}>{user.tesla_profile_linked ? 'Tesla-Profil erneut laden' : 'Mit Tesla verknüpfen'}<ArrowUpRight size={17}/></a> : <p className="hint">Die Verknüpfung benötigt eine aktive Fahrt und eine eingerichtete Tesla-Anmeldung.</p>}
        {user.tesla_profile_linked && <button disabled={avatarBusy} onClick={async()=>{setAvatarBusy(true);try {await api('/api/me/tesla-profile-link','DELETE');await reload();notify('Tesla-Profilverknüpfung entfernt.');}catch(error){notify((error as Error).message);}finally{setAvatarBusy(false);}}}>Tesla-Verknüpfung entfernen</button>}
      </section>}
      {!guest && <>
        <section className="panel">
          <h3>So finden dich deine Freunde</h3>
          <div className="profile-identity"><Avatar name={user.display_name} url={user.avatar_url} className="profile-avatar" /><div><strong>{user.display_name}</strong><small>{user.avatar_url ? 'Profilbild aus deinem Tesla-Konto' : 'Initialen, solange kein Profilbild verfügbar ist'}</small></div></div>
          {user.provider === 'tesla' && <button disabled={avatarBusy} onClick={() => void refreshAvatar()}><RefreshCw size={16} />{avatarBusy ? 'Profilbild wird geladen …' : 'Tesla-Profilbild laden'}</button>}
          <ActionForm onSubmit={async data => { await api('/api/me', 'PATCH', { username: data.get('username'), display_name: data.get('name'), plate: data.get('plate') }); await reload(); notify('Profil gespeichert.'); }}>
            <Field label="Anzeigename" name="name" value={user.display_name} /><Field label="Benutzername" name="username" value={user.username} /><Field label="Kennzeichen (optional)" name="plate" required={false} value={user.plate || ''} />
          </ActionForm>
        </section>
        <section className="panel">
          <div className="panel-heading"><Car size={21} /><h3>Deine Tesla-Fahrzeuge</h3></div>
          <button onClick={() => void api('/api/vehicles/sync', 'POST').then(reload).catch(e => notify(e.message))}><RefreshCw size={17} />Fahrzeuge abrufen</button>
          <div className="stack vehicle-list">{vehicles.map(vehicle => <div className="vehicle-card" key={vehicle.id}><div><Car size={26} /><strong>{vehicle.name}</strong><small>{vehicle.model}</small></div><button className={user.favorite_vehicle === vehicle.id ? 'selected' : ''} onClick={() => void api(`/api/vehicles/${encodeURIComponent(vehicle.id)}/select`, 'POST').then(reload).catch(e => notify(e.message))}>{user.favorite_vehicle === vehicle.id ? <Check size={17} /> : null}{user.favorite_vehicle === vehicle.id ? 'Standardfahrzeug' : 'Auswählen'}</button></div>)}</div>
          <p className="hint">Tesla muss den Fahrzeugzugriff freigeben. Ein schlafendes Fahrzeug wird nicht automatisch geweckt.</p>
        </section>
        <section className="panel" aria-label="Persönliche API-Schlüssel">
          <div className="panel-heading"><KeyRound size={21} /><h3>Persönliche API-Schlüssel</h3></div>
          <p>Für deine eigenen Integrationen und Telemetrie-Importe. Schlüssel werden nur einmal angezeigt und können jederzeit widerrufen werden.</p>
          <a className="button" href="/api-docs">Alle API-Endpunkte & LLM-Kopierfunktion<ArrowUpRight size={17} /></a>
          <ActionForm label="Schlüssel erzeugen" onSubmit={async data => { const result = await api('/api/keys', 'POST', { label: data.get('label'), days: unlimited ? null : Number(data.get('days')) }); setNewKey(result.token); await loadKeys(); }}>
            <Field label="Bezeichnung" name="label" placeholder="Meine Integration" />
            <label className="checkbox-field"><input type="checkbox" checked={unlimited} onChange={event => setUnlimited(event.target.checked)} /><span>Ohne Ablaufdatum</span></label>
            {!unlimited && <Field label="Gültigkeit in Tagen (1–365)" name="days" type="number" value="30" />}
          </ActionForm>
          {newKey && <CopyValue value={newKey} />}
          {keys.map(key => <div className="list-row" key={key.id}><div><strong>{key.label}</strong><small>{key.expires_at === null ? 'Ohne Ablaufdatum' : 'Bis ' + date(key.expires_at)}</small></div><button onClick={() => void api(`/api/keys/${key.id}`, 'DELETE').then(loadKeys).catch(e => notify(e.message))}>Widerrufen</button></div>)}
        </section>
        <section className="panel">
          <div className="panel-heading"><Shield size={21} /><h3>Dein Server</h3></div><p>Die Administration meldet sich separat über den konfigurierten OIDC-Anbieter an. Fahrer erhalten dadurch keine Administratorrechte.</p>
          <a className="button" href="/admin">Administration öffnen<ArrowUpRight size={17} /></a><a className="text-link" href="https://github.com/Baodor/TeslaTalk" target="_blank" rel="noreferrer">Quellcode · AGPLv3<ArrowUpRight size={15} /></a>
        </section>
        <VehicleNavigation vehicle={vehicles.find(vehicle => vehicle.id === user.favorite_vehicle)} />
      </>}
    </div>
  </>;
}

function GuestPage({ inviteKey }: { inviteKey: string }) {
  const [info, setInfo] = useState<any>(null), [error, setError] = useState('');
  const [register, setRegister] = useState(true);
  useEffect(() => { api('/api/guest/' + inviteKey).then(setInfo).catch(e => setError(e.message)); }, [inviteKey]);
  return <main className="center"><section className="entry-card"><Brand /><span className="eyebrow">MITFAHRER-ZUGANG</span><h1>{info?.title || 'Gemeinsam mitfahren.'}</h1>{error ? <p className="error">{error}</p> : !info ? <p>Einladung wird geladen …</p> : <><p>{date(info.starts_at)} – {date(info.ends_at)}</p>{info.active ? <div className="stack"><div className="segmented"><button type="button" className={register ? 'selected' : ''} aria-pressed={register} onClick={() => setRegister(true)}>Neu registrieren</button><button type="button" className={!register ? 'selected' : ''} aria-pressed={!register} onClick={() => setRegister(false)}>Bereits registriert? Anmelden</button></div><ActionForm key={register ? 'register' : 'login'} label={register ? 'Registrieren & mitfahren' : 'Als Mitfahrer anmelden'} onSubmit={async data => {
    if (register && data.get('pin') !== data.get('confirm')) throw new Error('Die beiden PINs stimmen nicht überein.');
    const result = await api(`/api/guest/${inviteKey}/${register ? 'register' : 'login'}`, 'POST', { name: data.get('name'), pin: data.get('pin') });
    location.assign('/trip/' + result.trip_id);
  }}><label className="field"><span>Dein Name</span><input name="name" required maxLength={60} autoComplete="username" /></label><label className="field"><span>{register ? 'Eigenen PIN wählen (6 Ziffern)' : 'Dein persönlicher PIN'}</span><input name="pin" type="password" required inputMode="numeric" pattern="[0-9]{6}" minLength={6} maxLength={6} autoComplete={register ? 'new-password' : 'current-password'} /></label>{register && <label className="field"><span>PIN wiederholen</span><input name="confirm" type="password" required inputMode="numeric" pattern="[0-9]{6}" minLength={6} maxLength={6} autoComplete="new-password" /></label>}<p className="hint">{register ? 'Wähle deinen Namen und deinen eigenen PIN. Merke dir beides für die nächste Anmeldung.' : 'Nutze deinen registrierten Namen und PIN; vorhandene Einladungen mit einem PIN vom Fahrtleiter funktionieren weiterhin.'} Dein Zugang endet automatisch mit der Fahrt.</p></ActionForm></div> : <div className="notice"><Clock size={22} /><span>Der Zugang ist nur innerhalb des Fahrtzeitraums verfügbar.</span></div>}<small>Kein Tesla-Konto erforderlich.</small></>}</section></main>;
}

function PublicPage({ shareKey }: { shareKey: string }) {
  const [trip, setTrip] = useState<any>(null), [error, setError] = useState('');
  useEffect(() => { api('/api/public/' + shareKey).then(setTrip).catch(e => setError(e.message)); }, [shareKey]);
  return <main className="center"><section className="entry-card public-card"><Brand /><span className="eyebrow">EIN GETEILTER ROADTRIP</span><h1>{trip?.title || 'Eine gemeinsame Erinnerung.'}</h1>{error ? <p className="error">{error}</p> : trip ? <><p><MapPin size={18} />{trip.destination || 'Gemeinsam unterwegs'}</p><p>{date(trip.starts_at)} – {date(trip.ends_at)}</p><div className="notice"><Shield size={21} /><span>Öffentliche Ansicht · nur lesbar<small>Private Nachrichten und Fahrzeugdaten bleiben in der Gruppe.</small></span></div><section className="album-preview"><Images size={36} /><h3>{trip.album.name}</h3><p>Das Fotoalbum folgt mit der Immich-Integration.</p></section></> : <p>Freigabe wird geladen …</p>}</section></main>;
}

function AdminPage({ config }: { config: any }) {
  const [info, setInfo] = useState<any>(null), [error, setError] = useState('');
  const [pushBusy, setPushBusy] = useState(false), [pushStatus, setPushStatus] = useState('');
  useEffect(() => { api('/api/admin').then(setInfo).catch(e => setError(e.message)); }, []);
  async function sendServerTest() {
    if (pushBusy) return;
    setPushBusy(true); setPushStatus('');
    try {
      const result = await api<{ queued_devices: number; queued_accounts: number }>('/api/admin/push/test', 'POST');
      setPushStatus(result.queued_devices
        ? `Testnachricht für ${result.queued_devices} Geräte in ${result.queued_accounts} Konten eingeplant. Die Zustellung erfolgt im Hintergrund.`
        : 'Keine Geräte mit aktivierten Benachrichtigungen und gültiger Anmeldung vorhanden.');
    } catch (error) { setPushStatus((error as Error).message); }
    finally { setPushBusy(false); }
  }
  return <main className="admin-layout">
    <header><Brand /><a href="/" className="button"><ArrowLeft size={16} />Zur Anwendung</a></header>
    <section className="panel"><span className="eyebrow">ADMINISTRATION</span><h1>Dein TeslaTalk-Server.</h1>
      {info ? <>
        <div className="summary-strip"><div><Users size={20} /><strong>{info.users}</strong><span>Konten</span></div><div><Route size={20} /><strong>{info.trips}</strong><span>Fahrten</span></div><div><Navigation size={20} /><strong>{info.samples}</strong><span>Messpunkte</span></div></div>
        <div className="list-row"><span>Tesla Fleet API</span><span className="badge">{info.tesla_ready ? 'KONFIGURIERT' : 'EINRICHTUNG FEHLT'}</span></div>
        <div className="list-row"><span>Sprachfunk</span><span className="badge">{info.voice_ready ? 'KONFIGURIERT' : 'EINRICHTUNG FEHLT'}</span></div>
        <div className="list-row"><span>Abfrageintervall bei verbundenen Fahrern</span><strong>{info.poll_interval} Sekunden</strong></div>
        <div className="list-row"><span>Speicherung</span><strong>{info.storage}</strong></div>
        <section aria-label="Server-Benachrichtigungen">
          <h2>Benachrichtigungen testen</h2>
          <p>Eine Testnachricht an alle Geräte auf diesem Server mit aktivierten Benachrichtigungen und gültiger Anmeldung senden, einschließlich installierter Web-Apps.</p>
          <button onClick={() => void sendServerTest()} disabled={pushBusy || !info.push_ready}><Send size={17} />{pushBusy ? 'Versand wird eingeplant …' : 'Testnachricht an alle Geräte'}</button>
          <p className="hint" role="status">{pushStatus || (info.push_ready ? 'Mitfahrer werden nur während ihrer gültigen Fahrt berücksichtigt.' : 'Web-Push ist noch nicht eingerichtet. VAPID-Schlüssel in der Serverkonfiguration hinterlegen.')}</p>
        </section>
        <AdminUsers />
        <p className="hint">Serverkonfiguration und Integrationsgeheimnisse werden über die Umgebungsvariablen der Installation verwaltet.</p>
        <button onClick={() => void api('/auth/logout', 'POST').then(() => location.reload())}>Abmelden</button>
      </> : <>
        <p>{error || 'Administratorzugang wird geprüft …'}</p>
        {config.admin_ready ? <a className="button primary" href="/auth/admin">Über OIDC anmelden<ArrowUpRight size={18} /></a> : <div className="notice"><Settings size={22} /><span>OIDC ist noch nicht eingerichtet.<small>Issuer, Client-ID und Administratorgruppe in der Serverkonfiguration hinterlegen.</small></span></div>}
      </>}
    </section>
  </main>;
}
