export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}
export async function api<T = any>(path: string, method = 'GET', body?: unknown, options: Pick<RequestInit, 'keepalive'> = {}): Promise<T> {
  const response = await fetch(path, { ...options, method, credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Verbindung fehlgeschlagen.' }));
    throw new ApiError(typeof error.detail === 'string' ? error.detail : 'Bitte Eingaben prüfen.', response.status);
  }
  return response.json();
}
export const date = (value: number) => new Date(value * 1000).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' });
export const duration = (value: number) => `${Math.floor(value / 3600)} h ${Math.floor(value % 3600 / 60)} min`;
export const localDate = (value: Date) => new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
export type User = { id: string; username: string; display_name: string; plate: string | null; favorite_vehicle: string | null; provider: string; avatar_url?: string | null };
export type Trip = { id: string; leader_id: string; title: string; destination: string; starts_at: number; ends_at: number; finished_at: number | null; status: string; participants: number };
export type Participant = User & { role: string; vehicle_id: string | null; vehicle_name: string; model: string; online: boolean; left_at: number | null; data: Record<string, any>; personal_location: { latitude: number; longitude: number; updated_at: number; speed_kmh: number | null; heading: number | null } | null };
