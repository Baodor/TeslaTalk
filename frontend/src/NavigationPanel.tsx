import { t, getLocale } from './i18n';
import { useEffect, useState } from 'react';
import { Route, RefreshCw, Battery, Clock, MapPin } from 'lucide-react';
import { api, date, type NavigationData } from './api';

export default function NavigationPanel({ navigation, fetchRoute, shared = false, finished = false }: {
  navigation: NavigationData | null; fetchRoute?: () => Promise<void>;
  shared?: boolean; finished?: boolean;
}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function act(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError('');
    try { await action(); } catch (error) { setError((error as Error).message); } finally { setBusy(false); }
  }
  const active = navigation?.status === 'active';
  const stale = navigation && Date.now()/1000-navigation.updated_at > 300;
  return <section className="panel navigation-panel" aria-label={shared ? t("Gemeinsame Fahrzeugroute") : t("Eigene Fahrzeugroute")}>
    <div className="panel-heading"><Route size={21} /><h3>{shared ? t("Berechnete Gruppenroute") : t("Route aus deinem Auto")}</h3>{navigation?.source === 'demo' && <span className="badge amber">{t("DEMO")}</span>}</div>
    <p>{shared ? t("Die Navigation des ausgewählten Planungsfahrzeugs wird automatisch für diese Gruppe angezeigt.") : t("Lies das aktuelle Navigationsziel deines Standardfahrzeugs. Dieser Abruf bleibt privat.")}</p>
    {active && <>
      <strong className="navigation-destination"><MapPin size={18} />{navigation.destination || t("Navigationsziel")}</strong>
      {navigation.destination_latitude !== null && navigation.destination_longitude !== null && <small>{t("Zielkoordinaten: ")}{navigation.destination_latitude.toFixed(5)}, {navigation.destination_longitude.toFixed(5)}</small>}
      <dl className="navigation-metrics">
        {navigation.distance_remaining_km !== null && <div><dt>{t("Reststrecke")}</dt><dd>{navigation.distance_remaining_km.toLocaleString(getLocale())} {t(" km")}</dd></div>}
        {navigation.minutes_remaining !== null && <div><dt><Clock size={14} />{t("Restzeit")}</dt><dd>{Math.ceil(navigation.minutes_remaining)} {t(" min")}</dd></div>}
        {navigation.arrival_at !== null && <div><dt>{t("Ankunft")}</dt><dd>{date(navigation.arrival_at)}</dd></div>}
        {navigation.battery_arrival_pct !== null && <div><dt><Battery size={14} />{t("Akku bei Ankunft")}</dt><dd>{navigation.battery_arrival_pct} %</dd></div>}
        {navigation.traffic_delay_minutes !== null && <div><dt>{t("Verkehrsverzögerung")}</dt><dd>{Math.ceil(navigation.traffic_delay_minutes)} {t(" min")}</dd></div>}
      </dl>
      <p className="hint">{navigation.route_points.length > 1 ? t("Der genaue Straßenverlauf aus Fleet Telemetry ist verfügbar.") : t("Tesla liefert hier das Ziel und verfügbare Kennzahlen. Für den genauen Straßenverlauf ist ein Fleet-Telemetry-Import erforderlich.")}</p>
    </>}
    {navigation?.status === 'inactive' && <p className="hint">{t("Im Auto ist keine Navigation aktiv. Starte eine Route im Auto und rufe sie erneut ab.")}</p>}
    {navigation?.status === 'unavailable' && <p className="hint">{t("Tesla liefert derzeit keine Navigationsdaten. Navigation im Auto starten und erneut abrufen; alternativ Fleet Telemetry anbinden.")}</p>}
    {!navigation && <p className="hint">{shared ? t("Wähle zuerst ein Planungsfahrzeug. Die Gruppenroute erscheint nach der Berechnung im Auto.") : t("Noch keine Navigationsdaten abgerufen.")}</p>}
    {navigation && <small className="navigation-updated">{finished ? t("Letzter Stand der abgeschlossenen Fahrt") : stale ? t("Veralteter Stand – erneut abrufen") : t("Stand")}: {date(navigation.updated_at)} · {navigation.source === 'telemetry' ? t("Fleet Telemetry") : navigation.source === 'demo' ? t("Demodaten") : t("Tesla Fleet API")}</small>}
    <div className="header-actions">
      {fetchRoute && <button disabled={busy} onClick={() => void act(fetchRoute)}><RefreshCw size={16} />{busy ? t("Route wird abgerufen …") : shared ? t("Berechnete Route aktualisieren") : t("Route aus Auto abrufen")}</button>}
    </div>
    {error && <p className="error" role="alert">{t(error)}</p>}
  </section>;
}

export function VehicleNavigation({ vehicle }: { vehicle: any }) {
  const [navigation, setNavigation] = useState<NavigationData | null>(vehicle?.data?.navigation || null);
  useEffect(() => { setNavigation(vehicle?.data?.navigation || null); }, [vehicle?.id]);
  return <NavigationPanel navigation={navigation} fetchRoute={vehicle ? async () => {
    setNavigation(await api<NavigationData>(`/api/vehicles/${encodeURIComponent(vehicle.id)}/navigation/refresh`, 'POST'));
  } : undefined} />;
}
