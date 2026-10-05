import { useState } from 'react';
import { Battery, Route, Car, AlertCircle, Check, RefreshCw } from 'lucide-react';
import { api, date, type NavigationData } from './api';
import NavigationPanel from './NavigationPanel';

type Vehicle = { user_id: string; vehicle_id: string; display_name: string; vehicle_name: string; model: string;
  battery_pct: number | null; range_km: number | null; updated_at: number | null;
  accepted: boolean; can_plan: boolean; is_planner: boolean; status: string; problem: string | null };
type Overview = { planner_user_id: string | null; vehicles: Vehicle[];
  recommendations: { lowest_battery_user_id: string | null; lowest_range_user_id: string | null } };
const statuses: Record<string,string> = {not_accepted:'Noch nicht zugestimmt',waiting:'Wartet auf Gruppenroute',sending:'Ziel wird gesendet',planning:'Tesla berechnet die Route',source_ready:'Berechnete Route ist die Gruppenroute',unconfirmed:'Ziel gesendet · Strecke unbestätigt',matching:'Straßenverlauf innerhalb Vergleichstoleranz',different:'Route prüfen',error:'Übertragung fehlgeschlagen'};
const problems: Record<string,string> = {different_route:'Dieser Tesla hat einen abweichenden Verlauf berechnet.',cannot_follow:'Dieser Fahrer meldet: Die Route kann nicht gefahren werden.',insufficient_battery:'Tesla meldet einen negativen Akku bei Ankunft.',command_error:'Das Ziel konnte nicht an diesen Tesla übertragen werden.'};

export default function RoutePlanning({ tripId, userId, leader, active, finished, destination, navigation, overview, update }: {
  tripId: string; userId: string; leader: boolean; active: boolean; finished: boolean; destination: string;
  navigation: NavigationData | null; overview: Overview | undefined;
  update: (navigation: NavigationData | null | undefined, overview: Overview | undefined) => void;
}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [target, setTarget] = useState(destination);
  const rows=overview?.vehicles || [], mine=rows.find(row=>row.user_id===userId);
  const recommendedRange=rows.find(row=>row.user_id===overview?.recommendations.lowest_range_user_id);
  const recommendedBattery=rows.find(row=>row.user_id===overview?.recommendations.lowest_battery_user_id);
  async function act(path: string, body?: unknown, method='POST') {
    if (busy) return;
    setBusy(true);setError('');
    try {
      const result=await api(`/api/trips/${tripId}/${path}`,method,body);
      const detail=await api(`/api/trips/${tripId}`);
      update(result.navigation ?? detail.navigation, result.route_overview || detail.route_overview);
    } catch(error) {setError((error as Error).message);} finally {setBusy(false);}
  }
  const sorted=[...rows].sort((a,b)=>a.user_id===recommendedRange?.user_id?-1:b.user_id===recommendedRange?.user_id?1:a.user_id===recommendedBattery?.user_id?-1:b.user_id===recommendedBattery?.user_id?1:(a.range_km??Infinity)-(b.range_km??Infinity));
  return <section className="route-planning" aria-label="Routenplanung der Gruppe">
    <section className="panel route-recommendations"><div className="panel-heading"><Battery size={21}/><h3>Welches Auto gibt die Route vor?</h3></div>
      <p>Wähle zuerst das Fahrzeug für die Planung. Die Gruppe zeigt dessen berechnete Navigation automatisch an.</p>
      <div className="route-recommendation-grid">
        <div><span className="eyebrow">GERINGSTE REICHWEITE</span><strong>{recommendedRange ? `${recommendedRange.display_name} · ${recommendedRange.range_km} km` : 'Noch keine aktuellen Reichweiten'}</strong><small>Empfehlung für das Planungsfahrzeug</small></div>
        <div><span className="eyebrow">NIEDRIGSTER AKKUSTAND</span><strong>{recommendedBattery ? `${recommendedBattery.display_name} · ${recommendedBattery.battery_pct} %` : 'Noch keine aktuellen Akkustände'}</strong><small>Separate Empfehlung nach Akkustand</small></div>
      </div>
      <p className="hint">Gemeldete Reichweite ist keine Garantie der Reststrecke. Empfehlungen berücksichtigen nur Messwerte der letzten fünf Minuten.</p>
      {leader && active && <label className="field"><span>Zieladresse für die erste Planung</span><input value={target} maxLength={200} onChange={event=>setTarget(event.target.value)} placeholder="Adresse oder eindeutiger Zielort" /></label>}
      {mine && active && <div className="header-actions"><button disabled={busy} className={mine.accepted?'selected':''} onClick={()=>void act('route/accept',undefined,mine.accepted?'DELETE':'POST')}><Check size={16}/>{mine.accepted?'Automatische Zielübernahme beenden':'Automatische Zielübernahme in meinem Auto erlauben'}</button>
        {mine.accepted && <button disabled={busy} onClick={()=>void act('route/problem',{reason:'cannot_follow'})}><AlertCircle size={16}/>Mein Auto schafft diese Route nicht</button>}
        {mine.status==='error' && <button disabled={busy} onClick={()=>void act('route/accept')}><RefreshCw size={16}/>Übertragung erneut versuchen</button>}</div>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="route-vehicles">{sorted.map(row=><article className="route-vehicle" key={row.user_id}>
        <div className="route-vehicle-title"><Car size={22}/><strong>{row.display_name} · {row.vehicle_name}</strong>{row.is_planner && <span className="badge accent-badge">PLANT DIE ROUTE</span>}</div>
        <div className="vehicle-stats"><span>{row.model}</span><span><Battery size={14}/>{row.battery_pct === null ? 'Akku unbekannt' : `${row.battery_pct} %`}</span><span>{row.range_km === null ? 'Reichweite unbekannt' : `${row.range_km} km`}</span></div>
        <small>{statuses[row.status] || row.status}{row.updated_at && ` · Messwerte: ${date(row.updated_at)}`}</small>
        {row.problem && <p className="error" role="status">{problems[row.problem] || 'Route bitte prüfen'} {leader && row.problem !== 'command_error' && 'Du kannst die Route dieses Autos als neue Gruppenroute übernehmen.'}</p>}
        {leader && active && <div className="header-actions"><button disabled={busy || !row.can_plan || !target.trim()} onClick={()=>void act('route/plan',{planner_user_id:row.user_id,destination:target})}><Route size={16}/>Dieses Fahrzeug für Planung auswählen</button>
          {row.accepted && row.problem && row.problem !== 'command_error' && <button disabled={busy} onClick={()=>void act(`route/adopt/${encodeURIComponent(row.user_id)}`)}>Route dieses Autos übernehmen</button>}
          {!row.can_plan && <small>Dieser Fahrer muss die Zielübernahme zuerst erlauben.</small>}</div>}
      </article>)}</div>
      <p className="hint">Aktuell überträgt TeslaTalk das Ziel. Jeder Tesla plant selbst. Identische Ladestopps werden damit noch nicht übernommen oder bestätigt; dafür fehlen die vollständigen Ladeplan-Daten und deren Übertragung. Ein Straßenvergleich benötigt Fleet Telemetry und verwendet 200 m Toleranz; verschiedene Startpunkte können unbestätigt bleiben.</p>
    </section>
    <NavigationPanel navigation={navigation} shared finished={finished} fetchRoute={leader && active && overview?.planner_user_id ? async()=>{await act('navigation');} : undefined}/>
  </section>;
}
