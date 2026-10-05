import { useState, type FormEvent } from 'react';
import { api, type User } from './api';

export default function UsernameSetup({ user, complete }: { user: User; complete: (user: User) => void }) {
  const [username, setUsername] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError('');
    try {
      const account = await api<User>('/api/me', 'PATCH', { username, display_name: user.display_name, plate: user.plate || '' });
      complete(account);
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  return <main className="center"><section className="entry-card" aria-label="Tesla-Erstanmeldung">
    <span className="eyebrow">WILLKOMMEN BEI TESLATALK</span><h1>Wähle deinen Benutzernamen.</h1>
    <p>Dein Tesla-Konto ist verbunden. Mit deinem eindeutigen Benutzernamen finden dich Freunde und können dich zu Fahrten einladen.</p>
    <form className="stack" onSubmit={event => void submit(event)}>
      <label className="field"><span>Benutzername</span><input name="username" value={username} onChange={event => setUsername(event.target.value)} required minLength={3} maxLength={30} pattern={'[A-Za-z0-9_\\-]+'} autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus placeholder="z. B. roadtrip-max" /></label>
      <p className="hint">3–30 Zeichen: Buchstaben, Ziffern, Unterstrich oder Bindestrich. Groß- und Kleinschreibung unterscheiden keine Namen.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary" disabled={busy}>{busy ? 'Wird gespeichert …' : 'Benutzername speichern & weiter'}</button>
    </form>
    <button className="text-link" onClick={() => void api('/auth/logout', 'POST').then(() => location.reload())}>Abmelden</button>
  </section></main>;
}
