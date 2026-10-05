import { useEffect, useState } from 'react';
import { RefreshCw, Users } from 'lucide-react';
import Avatar from './Avatar';
import { api, date } from './api';
import './AdminUsers.css';

type Account = { id: string; provider: string; display_name: string; username: string; email: string | null;
  plate: string | null; avatar_url: string | null; created_at: number; last_login_at: number | null };

export default function AdminUsers() {
  const [users, setUsers] = useState<Account[]>([]), [busy, setBusy] = useState(true), [error, setError] = useState('');
  async function load() {
    setBusy(true);setError('');
    try { setUsers(await api<Account[]>('/api/admin/users')); }
    catch(error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, []);
  return <section className="admin-users" aria-label="Alle Benutzer">
    <div className="panel-heading"><Users size={21}/><h2>Alle Benutzer</h2><button onClick={() => void load()} disabled={busy}><RefreshCw size={16}/>Aktualisieren</button></div>
    <p className="hint">{users.length} Konten · Letzter Login wird seit diesem Update erfasst. Tesla-Mail und Profilbild erscheinen, soweit Tesla sie liefert.</p>
    {busy && <p>Benutzer werden geladen …</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {!busy && !error && <div className="table-scroll admin-users-table"><table>
      <thead><tr><th>Benutzer</th><th>Tesla-Mailadresse</th><th>Benutzername</th><th>Kennzeichen</th><th>Letzter Login</th></tr></thead>
      <tbody>{users.map(user => <tr key={user.id}>
        <td><div className="admin-user-person"><Avatar name={user.display_name} url={user.avatar_url}/><div><strong>{user.display_name}</strong><small>{user.provider === 'guest' ? 'Mitfahrer' : user.provider === 'tesla' ? 'Tesla' : 'Demo'}</small></div></div></td>
        <td>{user.email || '—'}</td><td>{user.username}</td><td>{user.plate || '—'}</td><td>{user.last_login_at === null ? 'Noch nicht erfasst' : date(user.last_login_at)}</td>
      </tr>)}</tbody>
    </table>{users.length === 0 && <p>Noch keine Benutzer registriert.</p>}</div>}
  </section>;
}
