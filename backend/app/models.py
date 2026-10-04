from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class Profile(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r'^[A-Za-z0-9_-]+$')
    display_name: str = Field(min_length=1, max_length=60)
    plate: str = Field(default='', max_length=20)


class Query(BaseModel):
    query: str = Field(min_length=2, max_length=100)


class TripCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    destination: str = Field(default='', max_length=200)
    starts_at: datetime
    ends_at: datetime

    @field_validator('starts_at', 'ends_at')
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError('Datum benötigt eine Zeitzone.')
        return value

    @model_validator(mode='after')
    def validate_period(self):
        if self.ends_at <= self.starts_at or (self.ends_at-self.starts_at).total_seconds() > 90*86400:
            raise ValueError('Fahrtzeitraum muss positiv und höchstens 90 Tage lang sein.')
        return self


class Join(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')


class PassengerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class GuestLogin(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    pin: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator('text')
    @classmethod
    def not_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Nachricht ist leer.')
        return value


class Sample(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    speed_kmh: float | None = Field(default=None, ge=0, le=350, allow_inf_nan=False)
    heading: float | None = Field(default=None, ge=0, le=360, allow_inf_nan=False)
    battery_pct: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    range_km: float | None = Field(default=None, ge=0, le=1500, allow_inf_nan=False)
    odometer_km: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    energy_used_kwh: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    source: Literal['browser', 'telemetry'] = 'telemetry'

    @model_validator(mode='after')
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Breite und Länge müssen zusammen angegeben werden.')
        return self


class KeyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    days: int | None = Field(default=30, ge=1, le=365, description='null creates a key without an expiration date.')


class PushSubscription(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: dict[str, str]


class PushRemove(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
