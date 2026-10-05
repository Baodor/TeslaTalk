# TeslaTalk API · 0.1

All endpoints use the same server origin. Browser authentication uses an HttpOnly session cookie. Unsafe cookie-authenticated requests require `Origin` equal to `APP_URL`. Integrations can send `Authorization: Bearer <personal API key>`; an invalid key never falls back to cookies. Keys are displayed once and can be revoked from the profile. Choose a fixed lifetime of 1–365 days or no expiration with `days: null`. They inherit their owner's vehicle and trip permissions; an unlimited key never extends a trip's own time window.

The complete endpoint page is **`/api-docs`**, linked from **My profile → Personal API keys**. It loads the authenticated **`GET /api/docs`** catalog, including every registered API/auth route, the WebSocket, Tesla's public-key endpoint, access rules, parameters, request/response schemas and examples. **Copy all information for an LLM** copies the complete catalog and OpenAPI schema even when the page is filtered; it contains placeholders and static documentation, never actual account keys, sessions or vehicle data. A manual copy field and text download are available when clipboard access is denied.

The machine-readable schema is at **`GET /api/openapi.json`**, after a user sign-in or with a personal Bearer key. It includes authentication schemes and endpoint descriptions. `/api/health` and `/api/config` are public; neither returns secrets. The documentation data requires authentication.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/auth/tesla` | Begin official Tesla OAuth with bound, single-use state and PKCE |
| GET | `/auth/tesla/passenger?trip_id=...` | Link only the Tesla profile to the current active QR passenger browser session |
| GET | `/auth/tesla/callback` | Exchange code, create/find account, set browser session |
| GET | `/auth/admin` | Begin separate administrator OIDC flow |
| GET | `/auth/admin/callback` | Validate OIDC identity and authorization; set separate admin session |
| POST | `/auth/logout` | Revoke browser sessions and their push subscriptions |
| GET | `/api/health` | Public server health |
| GET | `/api/config` | Public readiness flags and public VAPID key |
| GET | `/api/docs` | Complete authenticated API/LLM catalog |
| GET | `/api/openapi.json` | Authenticated OpenAPI schema |
| POST | `/api/demo/login` | Demo-only sign-in using `query`; unavailable outside demo mode |
| GET / PATCH | `/api/me` | Own profile: username, display name, optional plate |
| POST | `/api/me/tesla-profile` | Refresh the current driver's optional Tesla account photo; at most three requests per minute |
| DELETE | `/api/me/tesla-profile-link` | Unlink the current active passenger's Tesla picture/email without changing QR identity or role |
| GET | `/api/vehicles` | Own cached vehicles |
| POST | `/api/vehicles/sync` | Retrieve account vehicles from Tesla |
| POST | `/api/vehicles/{vehicle_id}/select` | Select default vehicle |
| POST | `/api/vehicles/{vehicle_id}/refresh` | Retrieve own vehicle state, without waking it |
| POST | `/api/vehicles/{vehicle_id}/navigation/refresh` | Retrieve own navigation privately, without waking the car |
| PUT | `/api/vehicles/{vehicle_id}/navigation` | Owner Bearer-only complete navigation snapshot import, including optional Tesla `RouteLine` |
| GET / POST | `/api/friends` | List connections / request friendship using `query` |
| POST | `/api/friends/{user_id}/accept` | Accept an incoming request |
| DELETE | `/api/friends/{user_id}` | Remove a connection |
| GET / POST | `/api/trips` | Own trips / create with title, destination and timezone-aware dates |
| POST | `/api/trips/join` | Driver join using the six-digit PIN |
| GET | `/api/trips/{trip_id}` | Authorized trip details, members and recent per-trip vehicle data |
| POST | `/api/trips/{trip_id}/navigation` | Leader refreshes the already selected planning vehicle's automatically visible route |
| POST / DELETE | `/api/trips/{trip_id}/route/accept` | Driver consents to/revokes automatic destination reception in the own current car |
| POST | `/api/trips/{trip_id}/route/plan` | Leader selects an eligible planning member and sends a destination for initial calculation |
| POST | `/api/trips/{trip_id}/route/adopt/{user_id}` | Leader adopts a consenting driver's fresh calculated route as new group reference |
| POST | `/api/trips/{trip_id}/route/problem` | Consenting driver reports `different_route` or `cannot_follow` |
| POST / DELETE | `/api/trips/{trip_id}/controls/consent` | Active driver grants/revokes separate comfort control for the current own car; browser cookie only |
| POST | `/api/trips/{trip_id}/controls` | Active leader sends one whitelisted comfort action to explicitly confirmed consenting cars; browser cookie only |
| GET | `/api/trips/{trip_id}/controls/{request_id}` | Active leader reads saved batch status without resending any vehicle command |
| GET | `/api/invites` | Incoming trip invitations |
| POST | `/api/trips/{trip_id}/invite` | Leader invites an existing driver by exact username, plate or email |
| POST | `/api/trips/{trip_id}/accept` | Accept an invitation |
| POST | `/api/trips/{trip_id}/passengers` | Leader creates a named passenger and receives its PIN once |
| GET | `/api/guest/{invite_key}` | Public title and guest access window |
| POST | `/api/guest/{invite_key}/register` | Guest self-registration with own name and six-digit PIN, creates a trip-bound passenger session |
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
| POST | `/api/push/test` | Test own device with `endpoint` and optional subscription `keys`; rebind and send in one request; at most three tests per minute per user |
| GET | `/api/admin` | OIDC administrator's instance overview |
| GET | `/api/admin/users` | OIDC-admin-only user list including Tesla email, username, plate, picture and recorded last login |
| DELETE | `/api/admin/users/{user_id}` | OIDC-admin-only permanent account deletion after exact username confirmation |
| POST | `/api/admin/push/test` | OIDC admin queues a test for all active opted-in devices on the server; at most three broadcasts per minute |
| WebSocket | `/api/ws/trips/{trip_id}` | Authorized trip presence, messages and participant updates |
| GET | `/.well-known/appspecific/com.tesla.3p.public-key.pem` | Configured public Tesla vehicle key (PEM), or 404 |

### First Tesla sign-in, passengers and administrator data

`GET /api/me` includes `needs_username`. New Tesla accounts and migrated accounts still using their generated `fahrer-<id-prefix>` name must choose a username before driver actions. `PATCH /api/me` remains available for this setup; send `username`, `display_name` and optional `plate`. A username uses 3–30 ASCII letters/digits/underscores/hyphens and is globally unique without case distinction. Collision returns 409 and does not complete setup. A successful choice sets `needs_username:false`. Existing chosen names survive renewed Tesla logins.

The trip's QR link opens `/guest/<key>`. A passenger sends `POST /api/guest/{key}/register` with `{"name":"My name","pin":"<CHOSEN_SIX_DIGITS>"}` during the active trip. The PIN must contain exactly six ASCII digits; leading zeroes are retained. Names are trimmed and unique per trip without case distinction. Duplicate registration returns 409 without modifying existing credentials. Registration atomically creates a passenger identity/membership, sets an HttpOnly session expiring at trip end, returns only `trip_id` and broadcasts the group update. No Tesla account, vehicle or driver privileges are created. Registration allows 20 attempts per five minutes and IP/link.

`POST /api/guest/{key}/login` accepts that same name/PIN for subsequent sign-ins and also supports previously invited passengers. Attempts are limited to five per five minutes and IP/link/name, plus 60 per IP/link for a group sharing an IP. Login/registration are closed before trip start and after scheduled or early end. The UI confirms a newly chosen PIN before sending it. PINs are hashed; the PIN is never returned by self-registration or publicly listed.

`GET /api/admin/users` requires the separate OIDC administrator session; driver cookies/Bearer keys do not grant access. It returns every app account with `id`, `provider`, `display_name`, `username`, `email`, `plate`, `avatar_url`, `created_at` and `last_login_at`. Timestamps are Unix seconds. Missing email/plate/picture and older unrecorded login times remain `null`. Last login is updated by a successful Tesla, demo or passenger sign-in/registration, not by ordinary page reads. Tesla email/picture are refreshed on Tesla sign-in. The response excludes tokens, PIN hashes and vehicle locations; the LLM catalog includes its schema, no actual account rows.

### Passenger Tesla profile and account deletion

`GET /api/me` also returns `tesla_profile_linked`. Passenger linking requests only `openid user_data` and binds the single-use PKCE flow to the passenger's existing browser session, account and active trip. Missing or changed context fails closed; it never falls back to creating a driver session. No Tesla access/refresh token is retained and no vehicles are synchronized. QR identity, PIN and session deadline survive linking/unlinking. Linking an account that also belongs to an existing driver does not merge identities or grant driver rights.

`DELETE /api/admin/users/{user_id}` requires `{"username":"<EXACT_CURRENT_USERNAME>"}` and the independent admin cookie. It removes the user's sessions, API keys, tokens, vehicles, personal data and owned trips with their group data and orphan QR identities, atomically. Foreign trips remain, with the removed participant/planning car cleared. Active WebSockets are closed and persisted voice-removal jobs retry through the remaining lifetime of previously issued join tokens. It does not delete the external Tesla account or the separate OIDC administrator identity.

### Group comfort commands

The driver's comfort grant is independent of destination consent and binds one active trip and one own current car. Vehicle changes revoke it. Linked QR passengers and personal API keys cannot grant or send comfort actions. The leader must confirm a recipient list and send a fresh UUID with each deliberate action:

```json
{"request_id":"00000000-0000-4000-8000-000000000001","action":"climate_on","vehicle_ids":["<CURRENT_CONSENTING_VEHICLE_ID>"]}
```

Allowed actions are `frunk_open`, `rear_trunk_toggle`, `windows_vent`, `windows_close`, `climate_on`, `climate_off`. No arbitrary command/parameters are accepted. Results contain `request_id`, `action`, `status` (`running`/`completed`) and per-car `status` (`accepted`/`demo`/`skipped`/`error`/`unknown`/`pending`) and `message`. Repeating the same UUID/payload returns stored results; different data with that UUID returns 409. Changed recipients/consent and an already running batch also return 409. At most six new batches per minute. Read-only status retrieval never triggers a command.

Trunks/windows require fresh parked vehicle data; unknown state is skipped. Rear trunk control is an actuation, not an unconditional open/close promise; a frunk is closed manually. Actual commands use a TLS-verified official signed proxy, `vehicle_cmds` and enrolled virtual key. No wake-up or automatic retry after an ambiguous transport failure. See [setup](VEHICLE-CONTROLS.de.md).

### Vehicle navigation

Polling reads Tesla's `drive_state.active_route_destination`, `active_route_latitude/longitude`, `active_route_miles_to_arrival` (converted to kilometres), `active_route_minutes_to_arrival`, `active_route_energy_at_arrival` (percent) and `active_route_traffic_minutes_delay`. Missing/invalid optional numbers stay `null`; zero is retained. Missing navigation fields give `status: "unavailable"`; explicitly empty navigation gives `"inactive"` and clears the destination and line. An active navigation returns:

```json
{
  "status": "active",
  "destination": "Darmstadt Hauptbahnhof",
  "destination_latitude": 49.8728,
  "destination_longitude": 8.6289,
  "distance_remaining_km": 2.1,
  "minutes_remaining": 6,
  "arrival_at": 1791180720,
  "battery_arrival_pct": 76,
  "traffic_delay_minutes": 0,
  "route_points": [],
  "source": "fleet",
  "updated_at": 1791180360
}
```

`arrival_at` is calculated from the snapshot time and reported remaining minutes; it is a forecast. `route_points` contains latitude/longitude pairs only when the actual Tesla line is available. The app never draws a guessed road route or calls a third-party route planner. Tesla's official [available-data field mapping](https://developer.tesla.com/docs/fleet-api/fleet-telemetry/available-data) lists `RouteLine` exclusively under Fleet Telemetry; its encoding is standard Base64 of an ASCII Google polyline with precision **6**. The [vehicle-data endpoint](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-endpoints) requires `location_data` for location access and does not wake a sleeping car.

To provide the full line, an existing Fleet-Telemetry integration must assemble a **complete** snapshot and `PUT /api/vehicles/{vehicle_id}/navigation` with the owner's personal Bearer key. TeslaTalk does not deploy/configure a Tesla Telemetry receiver. Map `DestinationName`, `DestinationLocation`, `MilesToArrival` × 1.609344, `MinutesToArrival`, `ExpectedEnergyPercentAtTripArrival`, `RouteTrafficMinutesDelay`, and `RouteLine` to these fields:

```json
{
  "active": true,
  "destination": "Darmstadt Hauptbahnhof",
  "destination_latitude": 49.8728,
  "destination_longitude": 8.6289,
  "distance_remaining_km": 2.1,
  "minutes_remaining": 6,
  "battery_arrival_pct": 76,
  "traffic_delay_minutes": 0,
  "route_line": "<OPTIONAL_BASE64_POLYLINE6>",
  "captured_at": 1791180360
}
```

Replace `captured_at` with current measurement time in Unix seconds and omit `route_line` when unavailable. Invalid/cancelled telemetry must send `{"active":false,"captured_at":<current Unix seconds>}` with all route fields omitted. A new snapshot replaces the previous one; omitting `route_line` clears a previous line. Invalid Base64, truncated polylines, out-of-range coordinates, more than 20,000 points, an incomplete target coordinate pair or a snapshot older than 120 seconds/more than 30 seconds in the future give 422. Non-increasing telemetry timestamps give 409. Imports are capped at 30/minute per driver. Fresh telemetry is preferred for 120 seconds, including during ordinary car polling; afterwards a successful Fleet refresh replaces it. Failed upstream calls never invent a new snapshot.

The private navigation refresh and selected trip refresh share the existing vehicle refresh quota: five/minute per driver, with at least 60 seconds of Fleet cache. The group starts with `navigation: null`. Its `route_overview` contains `planner_user_id`, a vehicle list with `battery_pct`, `range_km`, measurement time, `accepted`, `status` and `problem`, plus independent `lowest_battery_user_id` and `lowest_range_user_id` recommendations. Only measurements at most five minutes old qualify. Unknown values are excluded; vehicle range is a reported estimate, not a guarantee of road range.

`POST /api/trips/{trip_id}/route/plan` takes `{"planner_user_id":"<MEMBER_USER_ID>","destination":"<ADDRESS>"}`. It requires an active trip and its leader. Another selected driver's current car needs prior consent through `POST .../route/accept`. Consent applies only to that member's own car and this trip; it is removed on vehicle change and can be withdrawn with `DELETE .../route/accept`. The leader's own car is also enrolled when the leader starts planning. The selected car receives the address first; its fresh vehicle response or telemetry becomes the group reference automatically. Command acceptance alone does not prove in-car calculation. Other consenting cars receive the reference destination once per destination change; errors require explicit owner retry, preventing command storms.

Real destination commands require `TESLA_NAVIGATION_COMMANDS=true`, Tesla-app authorization for `vehicle_cmds`, and reconnecting existing Tesla accounts so the new scope is granted. The only outbound navigation command is Tesla's REST `navigation_request`; this app does not expose arbitrary vehicle commands or wake up cars. If a command proxy is configured, destination requests use its verified HTTPS endpoint and optional CA; an invalid proxy is rejected and failures never cause a direct Fleet API retry. Tesla's official proxy forwards `navigation_request` through REST rather than converting it into a signed vehicle command. Public source information: [Tesla commands](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands) and [OAuth scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview). The physical-car behavior and app/virtual-key requirements must be verified on the installation.

**Identical charging stops are not implemented.** `route_overview.transfer_mode` is `destination_only`, and `charging_stops_confirmed` is `false`. Every Tesla calculates its own path and charging stops from the received destination. RouteLine alone is not an export of a complete ordered charging itinerary. No guessed waypoints or charging stops are sent. The desired identical group charging schedule needs an additional source/export of the planned stops and a supported transfer mechanism.

After consent, fresh route data can produce a deviation report: a different destination over 200 m away, negative reported battery-at-arrival, or a full-line geometric discrepancy beyond 200 m. Missing full lines, stale data and starts more than 1 km apart remain `unconfirmed`, not identical. The geometry comparison uses bounded sampling; it is not a proof of exact identity. A consenting driver can explicitly report `{"reason":"cannot_follow"}` or `{"reason":"different_route"}` through `POST .../route/problem`. The leader sees the affected member and receives one opt-in push per changed problem, with no location or destination in the notification. `POST .../route/adopt/{user_id}` selects that driver's fresh active navigation as the new reference. Public links still omit route data.

Selected routes update on the existing online-driver poll cycle or telemetry import. Finished trips keep the last snapshot privately; no more commands or live navigation updates are sent. All command access is checked again after token refresh, including membership, selected car, consent and trip expiry.

Own profiles and authorized trip participants include an optional `avatar_url`. The server accepts HTTPS image URLs from the Tesla account response; only the account owner can refresh their photo. Initials appear when Tesla supplies no image or the image fails to load. Public trip summaries omit these photos and participant identities.

The personal push test accepts the current browser's `PushSubscription.toJSON()` (`endpoint`, `keys.p256dh`, `keys.auth`). The server validates ownership, binds the subscription to the current browser session and sends in one request, without a preliminary subscribe request. An endpoint-only request remains compatible but requires an already registered subscription bound to that session. Each personal or administrative test uses a distinct notification tag.

The personal push test returns `accepted_by_provider: true`, `provider_accepted_at` (Unix seconds) and `provider_elapsed_ms` when the push service accepts the message. Acceptance does not prove display on the device. Expired device subscriptions return HTTP 410 and require reactivation. API keys cannot send push tests; passenger access ends with the trip.

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

WebSocket payloads contain a `type`: `participants`, `message`, `navigation`, `heartbeat`, or `ended`. A navigation event is `{"type":"navigation","navigation":<snapshot or null>}`. Authentication and guest expiry are checked at connection, periodically and before broadcasts. Audio is carried by LiveKit, not this WebSocket.

Photo uploads, Immich administration, arbitrary vehicle commands and synchronized charging itineraries are not implemented. Navigation retrieval, planning-car selection, consented destination sharing, deviation reports and Fleet Telemetry navigation imports are implemented.
