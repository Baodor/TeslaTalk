# TeslaTalk API · 0.1

All endpoints use the same server origin. Browser authentication uses an HttpOnly session cookie. Unsafe cookie-authenticated requests require `Origin` equal to `APP_URL`. Integrations can send `Authorization: Bearer <personal API key>`; an invalid key never falls back to cookies. Keys are displayed once and can be revoked from the profile. Choose a fixed lifetime of 1–365 days or no expiration with `days: null`. They inherit their owner's vehicle and trip permissions; an unlimited key never extends a trip's own time window.

The machine-readable schema is at **`GET /api/openapi.json`**, after a user sign-in. `/api/health` and `/api/config` are public; neither returns secrets. No unauthenticated interactive documentation is exposed.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/auth/tesla` | Begin official Tesla OAuth with bound, single-use state and PKCE |
| GET | `/auth/tesla/callback` | Exchange code, create/find account, set browser session |
| GET | `/auth/admin` | Begin separate administrator OIDC flow |
| POST | `/auth/logout` | Revoke browser sessions and their push subscriptions |
| GET / PATCH | `/api/me` | Own profile: username, display name, optional plate |
| POST | `/api/me/tesla-profile` | Refresh the current driver's optional Tesla account photo; at most three requests per minute |
| GET | `/api/vehicles` | Own cached vehicles |
| POST | `/api/vehicles/sync` | Retrieve account vehicles from Tesla |
| POST | `/api/vehicles/{vehicle_id}/select` | Select default vehicle |
| POST | `/api/vehicles/{vehicle_id}/refresh` | Retrieve own vehicle state, without waking it |
| GET / POST | `/api/friends` | List connections / request friendship using `query` |
| POST | `/api/friends/{user_id}/accept` | Accept an incoming request |
| DELETE | `/api/friends/{user_id}` | Remove a connection |
| GET / POST | `/api/trips` | Own trips / create with title, destination and timezone-aware dates |
| POST | `/api/trips/join` | Driver join using the six-digit PIN |
| GET | `/api/trips/{trip_id}` | Authorized trip details, members and recent per-trip vehicle data |
| GET | `/api/invites` | Incoming trip invitations |
| POST | `/api/trips/{trip_id}/invite` | Leader invites an existing driver by exact username, plate or email |
| POST | `/api/trips/{trip_id}/accept` | Accept an invitation |
| POST | `/api/trips/{trip_id}/passengers` | Leader creates a named passenger and receives its PIN once |
| GET | `/api/guest/{invite_key}` | Public title and guest access window |
| POST | `/api/guest/{invite_key}/login` | Guest name/PIN sign-in inside the scheduled interval |
| GET / POST | `/api/trips/{trip_id}/messages` | Read persistent chat / post before trip end |
| POST | `/api/trips/{trip_id}/samples` | Store an active-trip personal browser position (drivers and passengers) or vehicle telemetry (drivers only) |
| DELETE | `/api/trips/{trip_id}/location` | Stop sharing the current user's live person marker; vehicle position and history remain |
| GET | `/api/trips/{trip_id}/history` | Samples with `after_id` and `limit` pagination |
| GET | `/api/trips/{trip_id}/export` | Stream all captured samples as JSON |
| GET | `/api/trips/{trip_id}/ranking` | Measured consumption, captured duration and average speed |
| POST | `/api/trips/{trip_id}/voice-token` | Active member gets a microphone-only LiveKit room token |
| POST | `/api/trips/{trip_id}/finish` | Leader ends trip, closes guest access and voice room |
| POST / DELETE | `/api/trips/{trip_id}/share` | Create/replace or revoke a post-trip public read-only link |
| GET | `/api/public/{share_key}` | Read-only public summary, without participant identities or private data |
| GET / POST | `/api/keys` | List metadata / create personal key (`label`, `days`) |
| DELETE | `/api/keys/{key_id}` | Revoke own personal key |
| POST | `/api/push/subscribe` | Opt-in browser Web Push (`endpoint`, `keys.p256dh`, `keys.auth`) |
| POST | `/api/push/unsubscribe` | Revoke own device subscription by `endpoint` |
| POST | `/api/push/test` | Test own device by `endpoint`, bound to the current browser session; at most three tests per minute per user |
| GET | `/api/admin` | OIDC administrator's instance overview |
| POST | `/api/admin/push/test` | OIDC admin queues a test for all active opted-in devices on the server; at most three broadcasts per minute |
| WebSocket | `/api/ws/trips/{trip_id}` | Authorized trip presence, messages and participant updates |

Own profiles and authorized trip participants include an optional `avatar_url`. The server accepts HTTPS image URLs from the Tesla account response; only the account owner can refresh their photo. Initials appear when Tesla supplies no image or the image fails to load. Public trip summaries omit these photos and participant identities.

The push test returns `accepted_by_provider: true` when the push service accepts the message. Display still depends on the device's notification settings. Expired device subscriptions return HTTP 410 and require reactivation. API keys cannot send push tests; passenger access ends with the trip.

The separate admin broadcast returns `queued_accounts` and `queued_devices`; delivery runs through the persistent outbox. It targets registered devices with valid browser sessions, including installed web apps. Opted-out and expired devices are excluded; guests must have an active trip and are checked again before delivery. Queued counts do not confirm device delivery.

### Normalized sample

```json
{
  "source": "telemetry",
  "latitude": 49.8728,
  "longitude": 8.6512,
  "speed_kmh": 75,
  "heading": 90,
  "battery_pct": 78,
  "range_km": 386,
  "odometer_km": 12050.5,
  "energy_used_kwh": 1987.2
}
```

Telemetry samples require a driver's personal Bearer key. `energy_used_kwh` is a **cumulative measured counter**, not energy consumed by this one sample or an estimate from SOC. Odometer is cumulative kilometres. Unknown fields may be omitted; latitude/longitude must come as a pair. A browser sample uses `source: "browser"`, requires latitude and longitude, and can supply only personal location, speed and heading. Drivers and named passengers may share it during their own active trip. It never changes the vehicle's position, energy, SOC or odometer.

Each member in `participants_detail` and WebSocket `participants` has `data` for vehicle state and a separate `personal_location` object (or `null`). Both positions can appear simultaneously on the map. Live personal positions expire after five minutes without updates, disappear when explicitly stopped and are removed at trip end. Recorded browser samples remain in private trip history/export; personal and vehicle traces are drawn separately. Vehicle rankings exclude browser samples and passengers' positions.

For a key without an expiry, use `POST /api/keys` with `{"label":"My integration","days":null}`. Creation and listing return `expires_at: null`; fixed lifetimes return a Unix timestamp. The default remains 30 days when `days` is omitted. There is no total key-count cap; creation remains rate limited to prevent abuse. `DELETE /api/keys/{id}` revokes either kind immediately.

Consumption is `(last_energy - first_energy) / distance * 100`, only with valid counters and at least 1 km. Counter resets invalidate the affected metric. Duration is the captured sample interval; average speed is measured distance divided by that interval. These are recorded-section statistics, not charging-inclusive arrival forecasts. Tesla vehicle-data polling supplies no cumulative energy counter for ordinary passenger cars in this implementation; attach a suitable integration for consumption rankings.

Chat returns the latest 100 messages in chronological order. Use `before=<created_at>` for older messages. History defaults to 1,000 rows and caps each page at 5,000; the JSON export streams all rows. Failed authorization returns 401; driver-only or inactive-period actions return 403; trips outside your membership return 404. Identity, join, chat, key and sample actions are rate limited.

WebSocket payloads contain a `type`: `participants`, `message`, or `ended`. Authentication and guest expiry are checked at connection, periodically and before broadcasts. Audio is carried by LiveKit, not this WebSocket.

Photo uploads, Immich administration, vehicle commands and route planning have no V1 endpoints yet.
