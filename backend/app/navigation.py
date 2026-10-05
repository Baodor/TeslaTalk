"""Read-only navigation snapshots; Tesla RouteLine uses base64 + polyline6."""
import base64
import binascii
import math
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

TELEMETRY_MAX_AGE = 120
MAX_ROUTE_POINTS = 20_000


class Navigation(BaseModel):
    status: Literal['active', 'inactive', 'unavailable']
    destination: str | None = None
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    distance_remaining_km: float | None = None
    minutes_remaining: float | None = None
    arrival_at: float | None = None
    battery_arrival_pct: float | None = None
    traffic_delay_minutes: float | None = None
    route_points: list[tuple[float, float]] = Field(default_factory=list, description='Latitude/longitude pairs from the actual Tesla RouteLine; never an estimated route.')
    source: Literal['fleet', 'telemetry', 'demo']
    updated_at: float


def empty_navigation(source='fleet', status='unavailable', updated_at=None):
    return Navigation(status=status, source=source, updated_at=updated_at or time.time()).model_dump()


def from_fleet(drive):
    now = time.time()
    stamp = drive.get('timestamp')
    if isinstance(stamp,(int,float)) and not isinstance(stamp,bool) and math.isfinite(stamp):
        stamp = stamp/1000 if stamp > 100_000_000_000 else stamp
        if 0 < stamp <= now+30:
            now = stamp
    fields = {key: value for key, value in drive.items() if key.startswith('active_route_')}
    if not fields:
        return empty_navigation(updated_at=now)
    destination = fields.get('active_route_destination')
    destination = destination.strip()[:200] if isinstance(destination, str) and destination.strip() else None
    def number(key, minimum, maximum):
        value = fields.get('active_route_'+key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        return value if minimum <= value <= maximum else None
    latitude, longitude = number('latitude', -90, 90), number('longitude', -180, 180)
    if latitude is None or longitude is None:
        latitude = longitude = None
    if not destination and latitude is None:
        # Omitted fields differ from explicitly empty navigation. Do not reuse
        # a previous destination when the driver cancels the route.
        return empty_navigation(status='inactive', updated_at=now)
    miles, minutes = number('miles_to_arrival', 0, 100_000), number('minutes_to_arrival', 0, 100_000)
    return Navigation(status='active', destination=destination,
                      destination_latitude=latitude, destination_longitude=longitude,
                      distance_remaining_km=round(miles*1.609344, 1) if miles is not None else None,
                      minutes_remaining=minutes, arrival_at=now+minutes*60 if minutes is not None else None,
                      battery_arrival_pct=number('energy_at_arrival', -100, 100),
                      traffic_delay_minutes=number('traffic_minutes_delay', 0, 100_000),
                      source='fleet', updated_at=now).model_dump()


def decode_route_line(value):
    try:
        line = base64.b64decode(value, validate=True).decode('ascii')
    except (ValueError, UnicodeError, binascii.Error):
        raise ValueError('RouteLine benötigt gültiges Base64 mit einer Polyline in Genauigkeit 6.') from None
    points, position, latitude, longitude = [], 0, 0, 0
    def delta():
        nonlocal position
        result = 0
        for shift in range(0, 35, 5):
            if position >= len(line):
                break
            digit = ord(line[position])-63
            position += 1
            if not 0 <= digit <= 63:
                break
            result |= (digit & 31) << shift
            if digit < 32:
                return ~(result >> 1) if result & 1 else result >> 1
        raise ValueError('RouteLine enthält eine unvollständige oder ungültige Polyline.')
    while position < len(line):
        latitude += delta()
        longitude += delta()
        if not -90_000_000 <= latitude <= 90_000_000 or not -180_000_000 <= longitude <= 180_000_000:
            raise ValueError('RouteLine enthält ungültige Koordinaten.')
        points.append((latitude/1_000_000, longitude/1_000_000))
        if len(points) > MAX_ROUTE_POINTS:
            raise ValueError('RouteLine enthält mehr als 20.000 Punkte.')
    if len(points) < 2:
        raise ValueError('RouteLine benötigt mindestens zwei Punkte.')
    return points


class NavigationTelemetry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    active: bool
    destination: str | None = Field(default=None, max_length=200)
    destination_latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    destination_longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    distance_remaining_km: float | None = Field(default=None, ge=0, le=160_935, allow_inf_nan=False)
    minutes_remaining: float | None = Field(default=None, ge=0, le=100_000, allow_inf_nan=False)
    battery_arrival_pct: float | None = Field(default=None, ge=-100, le=100, allow_inf_nan=False)
    traffic_delay_minutes: float | None = Field(default=None, ge=0, le=100_000, allow_inf_nan=False)
    route_line: str | None = Field(default=None, max_length=220_000, description='Tesla RouteLine: standard base64 of an ASCII Google polyline, precision 6. Omit when unavailable.')
    captured_at: float = Field(allow_inf_nan=False, description='Unix seconds; no older than 120 seconds, at most 30 seconds in the future.')

    @model_validator(mode='after')
    def valid_route(self):
        if (self.destination_latitude is None) != (self.destination_longitude is None):
            raise ValueError('Zielkoordinaten müssen zusammen angegeben werden.')
        if self.destination is not None:
            self.destination = self.destination.strip() or None
        if self.active and not self.destination and self.destination_latitude is None:
            raise ValueError('Eine aktive Navigation benötigt einen Zielnamen oder Zielkoordinaten.')
        if not self.active and any(getattr(self, field) is not None for field in ('destination', 'destination_latitude', 'destination_longitude', 'distance_remaining_km', 'minutes_remaining', 'battery_arrival_pct', 'traffic_delay_minutes', 'route_line')):
            raise ValueError('Bei beendeter Navigation müssen Ziel, Kennzahlen und RouteLine entfallen.')
        if not -30 <= time.time()-self.captured_at <= TELEMETRY_MAX_AGE:
            raise ValueError('Navigationsdaten sind zu alt oder liegen in der Zukunft.')
        if self.route_line is not None:
            decode_route_line(self.route_line)
        return self

    def snapshot(self):
        if not self.active:
            return empty_navigation('telemetry', 'inactive', self.captured_at)
        return Navigation(status='active', source='telemetry', updated_at=self.captured_at,
                          route_points=decode_route_line(self.route_line) if self.route_line is not None else [],
                          arrival_at=self.captured_at+self.minutes_remaining*60 if self.minutes_remaining is not None else None,
                          **self.model_dump(exclude={'active', 'route_line', 'captured_at'})).model_dump()


def demo_navigation():
    return Navigation(status='active', destination='Demo: Darmstadt Hauptbahnhof',
                      destination_latitude=49.8728, destination_longitude=8.6289,
                      distance_remaining_km=2.1, minutes_remaining=6, arrival_at=time.time()+360,
                      battery_arrival_pct=76, traffic_delay_minutes=0, source='demo', updated_at=time.time()).model_dump()
