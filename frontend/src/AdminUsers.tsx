import { useEffect, useRef, useState } from 'react';
import { RefreshCw, Trash2, Users } from 'lucide-react';
import Avatar from './Avatar';
import { api, date } from './api';
import './AdminUsers.css';

type Account = { id: string; provider: string; display_name: string; username: string; email: string | null;
  plate: string | null; avatar_url: string | null; created_at: number; last_login_at: number | null };

export default function AdminUsers() {
  const [users, setUsers] = useState<Account[]>([]), [busy, setBusy] = useState(true), [error, setError] = useState('');
  const [deleting,setDeleting] = useState<Account | null>(null), [status,setStatus] = useState('');
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
    {status && <p role="status">{status}</p>}
    {!busy && !error && <div className="table-scroll admin-users-table"><table>
      <thead><tr><th>Benutzer</th><th>Tesla-Mailadresse</th><th>Benutzername</th><th>Kennzeichen</th><th>Letzter Login</th><th>Aktionen</th></tr></thead>
      <tbody>{users.map(user => <tr key={user.id}>
        <td><div className="admin-user-person"><Avatar name={user.display_name} url={user.avatar_url}/><div><strong>{user.display_name}</strong><small>{user.provider === 'guest' ? 'Mitfahrer' : user.provider === 'tesla' ? 'Tesla' : 'Demo'}</small></div></div></td>
        <td>{user.email || '—'}</td><td>{user.username}</td><td>{user.plate || '—'}</td><td>{user.last_login_at === null ? 'Noch nicht erfasst' : date(user.last_login_at)}</td>
        <td><button className="danger" aria-label={user.display_name+' löschen'} onClick={()=>setDeleting(user)}><Trash2 size={16}/>Löschen</button></td>
      </tr>)}</tbody>
    </table>{users.length === 0 && <p>Noch keine Benutzer registriert.</p>}</div>}
    {deleting && <DeleteAccount user={deleting} close={()=>setDeleting(null)} deleted={async()=>{setDeleting(null);setStatus(deleting.display_name+' wurde gelöscht.');await load();}}/>}
  </section>;
}

function DeleteAccount({user,close,deleted}:{user:Account;close:()=>void;deleted:()=>Promise<void>}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [confirmation,setConfirmation] = useState(''),[busy,setBusy] = useState(false),[error,setError] = useState('');
  useEffect(()=>{dialog.current?.showModal();},[]);
  return <dialog ref={dialog} className="modal" aria-labelledby="delete-account-title" onCancel={event=>{if(busy)event.preventDefault();else close();}}>
    <h2 id="delete-account-title">Benutzer dauerhaft löschen</h2>
    <p><strong>{user.display_name} (@{user.username})</strong> wird mit Profil, Tesla-Verknüpfung, Fahrzeugen, Nachrichten, Messwerten und Zugängen gelöscht.</p>
    <p className="error">Auch alle von diesem Benutzer geleiteten Fahrten mit ihren Gruppendaten und zugehörigen QR-Zugängen werden gelöscht. Das lässt sich nicht rückgängig machen.</p>
    <form className="stack" onSubmit={async event=>{
      event.preventDefault();if(busy||confirmation!==user.username)return;setBusy(true);setError('');
      try {await api('/api/admin/users/'+encodeURIComponent(user.id),'DELETE',{username:confirmation});await deleted();}
      catch(error) {setError((error as Error).message);setBusy(false);}
    }}>
      <label className="field"><span>Benutzername zur Bestätigung</span><input required autoComplete="off" value={confirmation} onChange={event=>setConfirmation(event.target.value)} placeholder={user.username}/></label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="header-actions"><button type="button" disabled={busy} onClick={close}>Abbrechen</button><button type="submit" className="danger" disabled={busy||confirmation!==user.username}>{busy?'Wird gelöscht …':'Dauerhaft löschen'}</button></div>
    </form>
  </dialog>;
}
