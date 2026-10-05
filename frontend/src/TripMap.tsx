import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap, Polyline } from 'react-leaflet';
import L from 'leaflet';
import { LocateFixed, MapPin } from 'lucide-react';
import type { Participant, NavigationData } from './api';
import { avatarSource, initials } from './Avatar';
import 'leaflet/dist/leaflet.css';

const colors = ['#ff6b72', '#95b9ff', '#f5c76d', '#e6a7d9', '#94dbec'];
function person(participant: Participant, color: string) {
  const marker = document.createElement('span');
  marker.style.background = color;
  marker.textContent = initials(participant.display_name);
  const source = avatarSource(participant.avatar_url);
  if (source) {
    const image = document.createElement('img');
    image.src = source; image.alt = ''; image.referrerPolicy = 'no-referrer';
    image.addEventListener('error', () => image.remove(), { once: true });
    marker.appendChild(image);
  }
  return L.divIcon({ className:'person-marker', iconSize:[40,40], iconAnchor:[-2,42], html:marker });
}
const car = (color: string) => L.divIcon({ className: 'car-marker', iconSize: [42, 42], iconAnchor: [21, 21],
  html: `<span style="background:${color}"><svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="#101a20" stroke-width="1.8"><path d="m5 10 2-5h10l2 5M4 10h16v7H4zM6 17v2m12-2v2M7 13h2m6 0h2"/></svg></span>` });

const destinationIcon = L.divIcon({ className: 'destination-marker', iconSize: [36, 36], iconAnchor: [18, 32],
  html: '<span aria-hidden="true">⚑</span>' });

function Controls({ positions, focusKey }: { positions: [number, number][]; focusKey: string }) {
  const map = useMap();
  const fitted = useRef<string | null>(null);
  function center() {
    if (positions.length === 1) map.setView(positions[0], 13, { animate: false });
    else if (positions.length > 1) map.fitBounds(positions, { padding: [60, 60], maxZoom: 13, animate: false });
  }
  useEffect(() => { if (fitted.current !== focusKey && positions.length) { center(); fitted.current = focusKey; } }, [positions, focusKey]);
  useEffect(() => {
    let active = true;
    const container = map.getContainer();
    const observer = new ResizeObserver(() => { if (active && container.isConnected) map.invalidateSize(); });
    observer.observe(container);
    return () => { active = false; observer.disconnect(); };
  }, [map]);
  return <button className="map-center" title="Gruppe zentrieren" aria-label="Gruppe zentrieren" onClick={center}><LocateFixed size={19} /></button>;
}

export default function TripMap({ participants, traces = [], navigation = null }: { participants: Participant[]; traces?: any[]; navigation?: NavigationData | null }) {
  const present = participants.filter(p => p.left_at === null);
  const vehicles = present.filter(p => p.vehicle_id && Number.isFinite(p.data.latitude) && Number.isFinite(p.data.longitude));
  const people = present.filter(p => p.personal_location && Number.isFinite(p.personal_location.latitude) && Number.isFinite(p.personal_location.longitude));
  const color = (id: string) => colors[Math.max(0, participants.findIndex(p => p.id === id)) % colors.length];
  const route = navigation?.status === 'active' ? navigation : null;
  const destination: [number, number] | null = route && route.destination_latitude !== null && route.destination_longitude !== null
    ? [route.destination_latitude, route.destination_longitude] : null;
  const positions: [number, number][] = [
    ...vehicles.map(p => [p.data.latitude, p.data.longitude] as [number, number]),
    ...people.map(p => [p.personal_location!.latitude, p.personal_location!.longitude] as [number, number]),
    ...(destination ? [destination] : []), ...(route?.route_points || [])
  ];
  const grouped: Record<string, { userId: string; personal: boolean; points: [number, number][] }> = {};
  traces.forEach(row => {
    if (!Number.isFinite(row.latitude) || !Number.isFinite(row.longitude)) return;
    const personal = row.source === 'browser', key = row.user_id + (personal ? ':person' : ':vehicle');
    (grouped[key] ??= { userId: row.user_id, personal, points: [] }).points.push([row.latitude, row.longitude]);
  });
  return <div className="map-wrap">
    {/* Leaflet's zoom transition timer can outlive map.remove() when changing tabs. */}
    <MapContainer center={[50.1109, 8.6821]} zoom={8} zoomControl={false} zoomAnimation={false} scrollWheelZoom className="trip-map">
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {destination && <Marker position={destination} icon={destinationIcon} title={'Navigationsziel: ' + (route?.destination || 'Ziel')}>
        <Popup><strong>Navigationsziel des Planungsfahrzeugs</strong><br />{route?.destination || 'Ziel aus dem Auto'}</Popup>
      </Marker>}
      {route && route.route_points.length > 1 && <Polyline positions={route.route_points} pathOptions={{ color: '#76d1b1', weight: 4, opacity: 0.9 }} />}
      {vehicles.map(p => <Marker key={'vehicle:' + p.id} position={[p.data.latitude, p.data.longitude]} icon={car(color(p.id))} title={'Fahrzeug: ' + p.display_name}>
        <Popup><strong>Fahrzeug · {p.vehicle_name || p.display_name}</strong><br />{p.display_name} · {p.model}<br />{p.data.battery_pct ?? '—'} % Akku</Popup>
      </Marker>)}
      {people.map(p => <Marker key={'person:' + p.id} position={[p.personal_location!.latitude, p.personal_location!.longitude]} icon={person(p, color(p.id))} zIndexOffset={500} title={'Person: ' + p.display_name}>
        <Popup><strong>Person · {p.display_name}</strong><br />{p.role === 'passenger' ? 'Mitfahrer' : 'Fahrer'} · geteilter Browser-Standort<br />Aktualisiert: {new Date(p.personal_location!.updated_at * 1000).toLocaleTimeString('de-DE')}</Popup>
      </Marker>)}
      {Object.entries(grouped).map(([key, trace]) => <Polyline key={key} positions={trace.points} pathOptions={{ color: color(trace.userId), weight: 3, dashArray: trace.personal ? '5 7' : undefined }} />)}
      <Controls positions={positions} focusKey={route ? `${route.destination}:${destination}:${route.route_points.length}` : 'group'} />
    </MapContainer>
    <div className="map-label"><span className="status-dot" /> NUR DEINE FAHRT</div>
    {(positions.length > 0 || traces.length > 0) && <div className="map-legend"><span className="legend-person" />Person<span className="legend-car" />Fahrzeug{destination && <><span className="legend-destination" />Ziel</>}{route && route.route_points.length > 1 && <><span className="legend-route" />Route</>}</div>}
    {!positions.length && !traces.length && <div className="map-empty"><MapPin size={22} /><span>Noch keine Standortdaten.<small>Fahrzeugdaten abrufen oder deinen persönlichen Standort teilen. Das geht auch als Mitfahrer.</small></span></div>}
  </div>;
}
