import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .config import settings

SCHEMA = '''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, provider TEXT NOT NULL, subject TEXT UNIQUE NOT NULL,
 username TEXT UNIQUE COLLATE NOCASE NOT NULL, display_name TEXT NOT NULL,
 email TEXT, plate TEXT UNIQUE, favorite_vehicle TEXT, created_at REAL NOT NULL, avatar_url TEXT
);
CREATE TABLE IF NOT EXISTS credentials (user_id TEXT PRIMARY KEY REFERENCES users(id), encrypted_token TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT, kind TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_states (state_hash TEXT PRIMARY KEY, binding_hash TEXT NOT NULL, verifier TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS vehicles (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL, model TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS friendships (low_id TEXT NOT NULL, high_id TEXT NOT NULL, requester TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL, PRIMARY KEY (low_id, high_id));
CREATE TABLE IF NOT EXISTS trips (
 id TEXT PRIMARY KEY, leader_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
 destination TEXT NOT NULL DEFAULT '', starts_at REAL NOT NULL, ends_at REAL NOT NULL,
 finished_at REAL, pin_hash TEXT UNIQUE NOT NULL, guest_key TEXT UNIQUE NOT NULL,
 public_key TEXT UNIQUE, voice_cleaned INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS members (trip_id TEXT NOT NULL REFERENCES trips(id), user_id TEXT NOT NULL REFERENCES users(id), role TEXT NOT NULL, vehicle_id TEXT, joined_at REAL NOT NULL, left_at REAL, PRIMARY KEY (trip_id,user_id));
CREATE TABLE IF NOT EXISTS invites (trip_id TEXT NOT NULL REFERENCES trips(id), user_id TEXT NOT NULL REFERENCES users(id), created_at REAL NOT NULL, PRIMARY KEY(trip_id,user_id));
CREATE TABLE IF NOT EXISTS passengers (id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id), name TEXT NOT NULL, normalized_name TEXT NOT NULL, pin_hash TEXT NOT NULL, user_id TEXT REFERENCES users(id), UNIQUE(trip_id,normalized_name));
CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id), user_id TEXT NOT NULL REFERENCES users(id), text TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS messages_trip ON messages(trip_id,created_at);
CREATE TABLE IF NOT EXISTS samples (
 id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id TEXT NOT NULL REFERENCES trips(id), user_id TEXT NOT NULL REFERENCES users(id),
 captured_at REAL NOT NULL, latitude REAL, longitude REAL, speed_kmh REAL, heading REAL,
 battery_pct REAL, range_km REAL, odometer_km REAL, energy_used_kwh REAL, source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS samples_trip_user ON samples(trip_id,user_id,captured_at);
CREATE TABLE IF NOT EXISTS personal_locations (
 trip_id TEXT NOT NULL REFERENCES trips(id), user_id TEXT NOT NULL REFERENCES users(id),
 updated_at REAL NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL, speed_kmh REAL, heading REAL,
 PRIMARY KEY (trip_id,user_id)
);
CREATE TABLE IF NOT EXISTS api_keys (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), token_hash TEXT UNIQUE NOT NULL, label TEXT NOT NULL, expires_at REAL NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS push_subscriptions (
 endpoint_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 session_hash TEXT NOT NULL REFERENCES sessions(token_hash) ON DELETE CASCADE,
 encrypted_subscription TEXT NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS push_outbox (
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES users(id),
 trip_id TEXT REFERENCES trips(id), payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 next_at REAL NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS push_deliveries (
 job_id INTEGER NOT NULL REFERENCES push_outbox(id) ON DELETE CASCADE,
 endpoint_hash TEXT NOT NULL,
 PRIMARY KEY (job_id,endpoint_hash)
);
CREATE INDEX IF NOT EXISTS push_due ON push_outbox(next_at);
'''


@contextmanager
def connect():
    connection = sqlite3.connect(settings.db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize():
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(SCHEMA)
        if 'avatar_url' not in {row['name'] for row in db.execute('PRAGMA table_info(users)')}:
            db.execute('ALTER TABLE users ADD COLUMN avatar_url TEXT')


def one(sql, args=()):
    with connect() as db:
        row = db.execute(sql, args).fetchone()
        return dict(row) if row else None


def all_rows(sql, args=()):
    with connect() as db:
        return [dict(row) for row in db.execute(sql, args).fetchall()]


def execute(sql, args=()):
    with connect() as db:
        return db.execute(sql, args).rowcount
