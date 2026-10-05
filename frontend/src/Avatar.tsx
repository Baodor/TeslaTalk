import { useState } from 'react';

export const initials = (name: string) => name.trim().split(/\s+/).slice(0, 2).map(part => Array.from(part)[0] || '').join('').toUpperCase() || '?';
export function avatarSource(url?: string | null) {
  if (!url) return undefined;
  try { const parsed = new URL(url); return parsed.protocol === 'https:' && !parsed.username && !parsed.password ? url : undefined; }
  catch { return undefined; }
}

export default function Avatar({ name, url, className = '' }: { name: string; url?: string | null; className?: string }) {
  const [failed, setFailed] = useState('');
  const source = avatarSource(url);
  return <div className={`avatar ${className}`} role="img" aria-label={`Profilbild von ${name}`}>
    <span>{initials(name)}</span>
    {source && source !== failed && <img src={source} alt="" referrerPolicy="no-referrer" onError={() => setFailed(source)} />}
  </div>;
}
