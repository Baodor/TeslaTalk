import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap, Polyline } from 'react-leaflet';
import L from 'leaflet';
import { LocateFixed, MapPin } from 'lucide-react';
import type { Participant } from './api';
import 'leaflet/dist/leaflet.css';

const colors = ['#ff6b72', '#95b9ff', '#f5c76d', '#e6a7d9', '#94dbec'];
const person = (color: string) => L.divIcon({ className: 'person-marker', iconSize: [28, 28], iconAnchor: [-2, 32],
  html: `<span style="background:${color}"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#101a20" stroke-width="2"><circle cx="12" cy="8" r="3"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/></svg></span>` });
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
  const present = participants.filter(p => p.left_at === null);
  const vehicles = present.filter(p => p.vehicle_id && Number.isFinite(p.data.latitude) && Number.isFinite(p.data.longitude));
  const people = present.filter(p => p.personal_location && Number.isFinite(p.personal_location.latitude) && Number.isFinite(p.personal_location.longitude));
  const color = (id: string) => colors[Math.max(0, participants.findIndex(p => p.id === id)) % colors.length];
  const positions: [number, number][] = [
    ...vehicles.map(p => [p.data.latitude, p.data.longitude] as [number, number]),
    ...people.map(p => [p.personal_location!.latitude, p.personal_location!.longitude] as [number, number])
  ];
  const grouped: Record<string, { userId: string; personal: boolean; points: [number, number][] }> = {};
  traces.forEach(row => {
    if (!Number.isFinite(row.latitude) || !Number.isFinite(row.longitude)) return;
    const personal = row.source === 'browser', key = row.user_id + (personal ? ':person' : ':vehicle');
    (grouped[key] ??= { userId: row.user_id, personal, points: [] }).points.push([row.latitude, row.longitude]);
  });
  return <div className="map-wrap">
    <MapContainer center={[50.1109, 8.6821]} zoom={8} zoomControl={false} scrollWheelZoom className="trip-map">
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {vehicles.map(p => <Marker key={'vehicle:' + p.id} position={[p.data.latitude, p.data.longitude]} icon={car(color(p.id))} title={'Fahrzeug: ' + p.display_name}>
        <Popup><strong>Fahrzeug · {p.vehicle_name || p.display_name}</strong><br />{p.display_name} · {p.model}<br />{p.data.battery_pct ?? '—'} % Akku</Popup>
      </Marker>)}
      {people.map(p => <Marker key={'person:' + p.id} position={[p.personal_location!.latitude, p.personal_location!.longitude]} icon={person(color(p.id))} zIndexOffset={500} title={'Person: ' + p.display_name}>
        <Popup><strong>Person · {p.display_name}</strong><br />{p.role === 'passenger' ? 'Mitfahrer' : 'Fahrer'} · geteilter Browser-Standort<br />Aktualisiert: {new Date(p.personal_location!.updated_at * 1000).toLocaleTimeString('de-DE')}</Popup>
      </Marker>)}
      {Object.entries(grouped).map(([key, trace]) => <Polyline key={key} positions={trace.points} pathOptions={{ color: color(trace.userId), weight: 3, dashArray: trace.personal ? '5 7' : undefined }} />)}
      <Controls positions={positions} />
    </MapContainer>
    <div className="map-label"><span className="status-dot" /> NUR DEINE FAHRT</div>
    {(positions.length > 0 || traces.length > 0) && <div className="map-legend"><span className="legend-person" />Person<span className="legend-car" />Fahrzeug</div>}
    {!positions.length && !traces.length && <div className="map-empty"><MapPin size={22} /><span>Noch keine Standortdaten.<small>Fahrzeugdaten abrufen oder deinen persönlichen Standort teilen. Das geht auch als Mitfahrer.</small></span></div>}
  </div>;
}
