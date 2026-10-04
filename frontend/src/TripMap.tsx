import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap, Polyline } from 'react-leaflet';
import L from 'leaflet';
import { LocateFixed, MapPin } from 'lucide-react';
import type { Participant } from './api';
import 'leaflet/dist/leaflet.css';

const colors = ['#8eefbb', '#95b9ff', '#f5c76d', '#e6a7d9', '#94dbec'];
const car = (color: string) => L.divIcon({ className: 'car-marker', iconSize: [42, 42], iconAnchor: [21, 21],
  html: `<span style="background:${color}"><svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="#101a20" stroke-width="1.8"><path d="m5 10 2-5h10l2 5M4 10h16v7H4zM6 17v2m12-2v2M7 13h2m6 0h2"/></svg></span>` });

function Controls({ positions }: { positions: [number, number][] }) {
  const map = useMap();
  const fitted = useRef(false);
  function center() {
    if (positions.length === 1) map.setView(positions[0], 13);
    else if (positions.length > 1) map.fitBounds(positions, { padding: [60, 60], maxZoom: 13 });
  }
  useEffect(() => { if (!fitted.current && positions.length) { center(); fitted.current = true; } }, [positions]);
  useEffect(() => { const observer = new ResizeObserver(() => map.invalidateSize()); observer.observe(map.getContainer()); return () => observer.disconnect(); }, [map]);
  return <button className="map-center" title="Gruppe zentrieren" aria-label="Gruppe zentrieren" onClick={center}><LocateFixed size={19} /></button>;
}

export default function TripMap({ participants, traces = [] }: { participants: Participant[]; traces?: any[] }) {
  const located = participants.filter(p => p.left_at === null && Number.isFinite(p.data.latitude) && Number.isFinite(p.data.longitude));
  const positions: [number, number][] = located.map(p => [p.data.latitude, p.data.longitude]);
  const grouped: Record<string, [number, number][]> = {};
  traces.forEach(row => { if (Number.isFinite(row.latitude) && Number.isFinite(row.longitude)) (grouped[row.user_id] ??= []).push([row.latitude, row.longitude]); });
  return <div className="map-wrap">
    <MapContainer center={[50.1109, 8.6821]} zoom={8} zoomControl={false} scrollWheelZoom className="trip-map">
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {located.map((p, i) => <Marker key={p.id} position={[p.data.latitude, p.data.longitude]} icon={car(colors[i % colors.length])}>
        <Popup><strong>{p.display_name}</strong><br />{p.model || 'Mitfahrer'}<br />{p.data.battery_pct ?? '—'} % Akku</Popup>
      </Marker>)}
      {Object.entries(grouped).map(([uid, points], i) => <Polyline key={uid} positions={points} pathOptions={{ color: colors[i % colors.length], weight: 3 }} />)}
      <Controls positions={positions} />
    </MapContainer>
    <div className="map-label"><span className="status-dot" /> NUR DEINE FAHRT</div>
    {!located.length && <div className="map-empty"><MapPin size={22} /><span>Noch keine Standortdaten.<small>Fahrzeugdaten abrufen oder Standort teilen.</small></span></div>}
  </div>;
}
