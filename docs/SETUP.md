# Running your own TeslaTalk server

TeslaTalk 0.1 is a preview implementation. The web application, API and demo can be run now. Production Tesla access requires the operator's Fleet API application, registration and permissions. Real vehicle/browser compatibility and delivery of notifications on physical iPhones and Android devices still need field testing.

## Local demo

Requirements: Git, Python 3, OpenSSL and Docker with Compose v2.

```bash
git clone https://github.com/Baodor/TeslaTalk.git
cd TeslaTalk
python3 scripts/configure.py --demo
docker compose up -d --build
```

Open `http://localhost:8780`. Demo sign-in creates clearly labelled sample vehicles. Use separate browser profiles to try two drivers. Named passengers can enter via the trip QR code and their own name/PIN during the scheduled interval.

The bootstrap script creates `.env`, `deploy/livekit.yaml`, VAPID keys and a Tesla EC key pair. It never prints keys, never overwrites an existing `.env` and uses restrictive permissions for secrets. Only the public Tesla key is mounted into the application. The Docker host creates and manages the SQLite data volume.

For Docker inside a VM, replace `APP_URL` and `LIVEKIT_URL` with reachable addresses. Microphones, location permission, service workers and Web Push require a secure context; `localhost` is the development exception. An HTTP LAN IP is insufficient.

For local audio testing set `rtc.use_external_ip: false` in `deploy/livekit.yaml` and, where needed, set `rtc.node_ip` to the host's reachable IP. Production hosts normally use `use_external_ip: true`.

## HTTPS deployment

Create two DNS records pointing to a public server: one for the application and one for LiveKit signalling. On a **new installation**:

```bash
python3 scripts/configure.py \
  --url https://talk.example.com \
  --voice-url wss://voice.example.com \
  --email you@example.com
docker compose -f compose.yaml -f deploy/compose.https.yaml up -d --build
```

The Caddy overlay obtains HTTPS certificates automatically. Forward ports **80/TCP, 443/TCP, 7881/TCP and 7882/UDP** to the host. The two app/signalling ports, 8780 and 7880, are bound to localhost in the base Compose file; Caddy reaches the services over the private Docker network. The 443/UDP mapping enables HTTP/3.

On an existing installation, edit `APP_URL`, `APP_HOST`, `LIVEKIT_URL`, `VOICE_HOST`, `VAPID_SUBJECT` and `DEMO_MODE` directly. Keep the existing `APP_SECRET`, VAPID keys and LiveKit keys. Run `docker compose ... up -d --build` with the same overlays afterwards. Keep `DEMO_MODE=false` for a real installation.

### Existing Traefik

The root [compose.traefik.yaml](../compose.traefik.yaml) is a complete deployment file for an existing Traefik; use it **on its own**. Traefik must already be connected to the external Docker network `proxy`, have a `websecure` entrypoint and provide valid TLS certificates for both domains. A [German step-by-step guide](START.de.md) covers the same setup.

On a **new installation**, point both DNS names below to your server, replace the email address and run:

```bash
python3 scripts/configure.py \
  --url https://teslatalk.glockb.de \
  --voice-url wss://teslatalk-voice.glockb.de \
  --email you@example.com
docker compose -f compose.traefik.yaml config --quiet
docker compose -f compose.traefik.yaml up -d --build
```

To use your own domains, pass them to the bootstrap script; its `APP_HOST` and `VOICE_HOST` values also configure the router rules. On an existing installation, edit `.env` while retaining existing secrets. Put your Tesla and optional administrator OIDC credentials in `.env` as described below. Settings changes require `up -d` to recreate the application container; `restart` alone does not reload environment variables.

The file uses `tls=true` and an explicit service for each router. TLS alone does not issue a trusted certificate. If your Traefik requires a per-router ACME resolver, set `TRAEFIK_CERT_RESOLVER=YOUR_RESOLVER` in `.env`; both routers use that exact existing resolver. This does not create a resolver in Traefik. Leave it empty for existing matching certificates or centrally configured TLS defaults. Set `PROXY_NETWORK` in `.env` only if your external Docker network has another name. The [German certificate diagnostics](START.de.md#https-zertifikatfehler-pr%C3%BCfen) cover browser certificate errors.

Application port **8780** and LiveKit signalling port **7880** are available over the Docker network only in this file. Open/forward **7881/TCP** and **7882/UDP** directly to the Docker host for audio. Traefik serves both domains over **443/TCP** and supports WebSocket connections.

For installations already using the base file, the original overlay remains available:

```bash
docker compose -f compose.yaml -f deploy/compose.traefik.yaml up -d --build
```

When switching from the base-plus-overlay setup to the complete file, keep the same project directory and any existing `-p` project name to retain your data volume. Do not combine the root Traefik file with the base or Caddy files. The overlay uses the same optional `TRAEFIK_CERT_RESOLVER` setting. An old `CERT_RESOLVER` variable is not read; move its value to `TRAEFIK_CERT_RESOLVER` if it names the resolver you use.

### Audio networking

HTTPS carries the application and LiveKit signalling, while actual audio uses WebRTC. A reverse proxy alone cannot carry the UDP media traffic. Restrictive mobile networks may require a separately configured TURN server; the default Compose setup does not include one. See [LiveKit's deployment guidance](https://docs.livekit.io/home/self-hosting/deployment/) and [port requirements](https://docs.livekit.io/home/self-hosting/ports-firewall/).

Do not enable `room.auto_create`. TeslaTalk creates authorized rooms through the internal server API, deletes them when a trip ends and issues microphone-only join tokens. Disabling automatic room creation prevents a retained LiveKit token from recreating a finished room. The application additionally disconnects audio at the end of the scheduled interval.

The default microphone control is a tap toggle: tap once to speak and again to mute. It stays enabled after touch/key release, and its active state is visibly labelled. In tap mode, leaving the page or disconnecting mutes the microphone. Optional voice activation remains available; multiple participants can speak concurrently.

If you see `could not establish signal connection: Load failed`, first check the **public** `LIVEKIT_URL` (`wss://...`) and its trusted HTTPS certificate. `LIVEKIT_INTERNAL_URL` (`http://livekit:7880`) is for the application server only. A `TRAEFIK DEFAULT CERT` cannot establish a trusted LiveKit connection. Run `python3 scripts/check_traefik.py` on the Docker host to see configured resolver names, public origins, network connectivity and internal target ports without displaying credentials. Set `TRAEFIK_CERT_RESOLVER` to the exact resolver name already configured in your Traefik; a Cloudflare DNS provider does not establish that name.

When using Cloudflare's proxy, check **Network → WebSockets** and rules affecting the voice domain. An extra login page, browser challenge or WAF rule may block the initial upgrade request. [Cloudflare's WebSocket documentation](https://developers.cloudflare.com/network/websockets/) explains the relevant checks. Only adjust a rule confirmed to block the connection. TLS and signalling must work before troubleshooting audio media ports.

## Tesla Fleet API

1. Create your own application at [Tesla's developer portal](https://developer.tesla.com/). Configure the allowed origin `https://talk.example.com` and exact callback `https://talk.example.com/auth/tesla/callback`.
2. Enable the account, vehicle data and location permissions used by V1. The authorization request uses `openid offline_access user_data vehicle_device_data vehicle_location`; it does not request vehicle command permissions.
3. Put the client ID and client secret in `.env`. The default `TESLA_FLEET_URL` is the EU/EMEA endpoint. Use `https://fleet-api.prd.na.vn.cloud.tesla.com` for North America/APAC outside China. This preview uses one configured region per server.
4. Start the HTTPS server and run `python3 scripts/register_tesla.py --check`. This checks configuration and validates the public secp256r1 EC key served at `https://talk.example.com/.well-known/appspecific/com.tesla.3p.public-key.pem` against your local public key. The check needs Python 3 and OpenSSL but does not register the application or validate the client credentials. The private key is never served.
5. Register the partner account in your configured region with `python3 scripts/register_tesla.py`. This explicitly sends the domain registration request to Tesla; it does not print or persist the partner token. Follow Tesla's [partner registration](https://developer.tesla.com/docs/fleet-api/endpoints/partner-endpoints) and [partner token](https://developer.tesla.com/docs/fleet-api/authentication/partner-tokens) documentation if your application requires a different onboarding flow.
6. Recreate TeslaTalk with `docker compose ... up -d` after changing `.env`, sign in via Tesla's own authorization page, then open your profile and retrieve/select your vehicle. A plain `restart` does not reload environment variables.

TeslaTalk stores encrypted OAuth tokens, not Tesla passwords. The initial driver account is created from Tesla's `/users/me` response. Vehicle access stays scoped to that signed-in account. An account with several vehicles can select a default; the selected vehicle is used for its current and upcoming trips.

V1 polls vehicle data only for connected drivers in active trips, normally every 120 seconds. Manual requests have a 60-second cache and rate limits. Sleeping vehicles are not automatically awakened. Requests may incur Fleet API charges: configure your budget in Tesla's portal. Tesla recommends Fleet Telemetry for frequent updates; a production Fleet Telemetry receiver is on the roadmap, while the existing personal-key sample API accepts normalized telemetry from your own integration.

Fields not supplied by Tesla stay unavailable. Consumption rankings need a measured **cumulative energy counter** and an odometer; battery percentage is not a substitute. Browser location sharing supplies position/speed only. Route mirroring, charging forecasts, waypoint commands, music pause/resume and Immich integration are not implemented in V1.

## Home-screen installation and notifications

TeslaTalk is a PWA. Visit **your own server address** in the phone browser, sign in and use **Mein Profil → Zum Home-Bildschirm**, or the browser's installation menu. The icon combines a Tesla-style T with a walkie-talkie. Notifications live under **Mein Profil → Benachrichtigungen & Web-App**, including for named passengers.

- **iPhone/iPad:** Safari → Share → Add to Home Screen. Launch from that icon, then explicitly enable notifications. Home-screen Web Push requires iOS/iPadOS 16.4 or newer.
- **Android/desktop Chrome:** Use the install button or browser menu, then enable notifications.
- **Firefox:** Web Push is supported where the browser exposes the required APIs; installation behaviour varies.

The interface checks capabilities and explains missing support. VAPID keys are generated by `configure.py`; use a real contact address in `VAPID_SUBJECT`. This implementation permits push endpoints from Apple, Mozilla and FCM. Internet access to the relevant push provider is required. Physical-device end-to-end delivery is a remaining acceptance check; browser consent and service-worker behaviour have automated tests, and server delivery/retry behaviour is tested with mocked push services.

Notifications cover trip invitations, friend requests and new chat messages. They exclude chat text, plates and location. Each device opts in separately, can revoke permission, and is tied to a valid browser session. Logout or session expiry removes its server subscription; reauthentication renews an existing browser subscription without another permission prompt. Guest subscriptions end no later than the trip and queued trip messages are checked again before dispatch.

The opt-in choice is remembered per account/device. A failed server sync never clears it. If the browser removes the subscription or blocks permission, the profile explains the problem and offers repair or deactivation. Removing website data resets local preferences; inspect and enable notifications again afterwards. The 180×180 Apple PNG is also available at `/apple-touch-icon.png` and `/apple-touch-icon-precomposed.png`. If an existing iPhone shortcut shows a letter, first fix HTTPS, then remove and recreate that Home Screen entry in Safari.

The service worker caches public assets and the offline page only. Trips, accounts, GPS history and chat responses are never cached. Audio, current maps and new messages need connectivity. Mobile browsers can suspend audio when the app goes into the background; PWA installation does not guarantee continuous background radio. Verify the intended behaviour on your phone and Tesla firmware.

The offline page now serves its cached CSS/icons and checks server health before reconnecting, preserving trip links. If a Mac keeps showing it after HTTPS is fixed, try a private Safari window. If that works, remove only this site's data via Safari → Settings → Privacy → Manage Website Data, then sign in again. [Apple's guidance](https://support.apple.com/en-us/102564).

Mobile page zoom is suppressed and input text is at least 16 px to avoid iOS focus zoom. Map zoom is separate. Browsers and operating-system accessibility tools may enforce their own display rules; physical-device verification is still required.

## Personal and vehicle locations

Choose **Standort teilen** during an active trip to share your own browser location, including as a named passenger. The map shows people as circular person markers and vehicle positions from Fleet/telemetry as separate car markers. They can appear at the same time; a browser position never replaces vehicle data. Stop sharing to remove the live person marker. Without fresh updates, it expires after five minutes; the private recorded history remains. Personal and vehicle history lines stay separate, and vehicle rankings use vehicle samples only.

## Personal API keys

In **Mein Profil → Persönliche API-Schlüssel**, choose **Ohne Ablaufdatum** for a key that stays valid until revoked, or choose a fixed lifetime of 1–365 days. There is no total key-count cap. Creation still has an abuse-prevention rate limit. Unlimited keys inherit the owner's permissions and cannot bypass trip boundaries. The API accepts `days: null` and returns `expires_at: null` for this option.

## OIDC administration

Use a **separate OIDC application** with callback `https://talk.example.com/auth/admin/callback`. Configure `OIDC_ISSUER`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET`. Grant access using the `teslatalk-admin` group (configurable with `ADMIN_GROUP`) or the `ADMIN_EMAILS` allowlist with a verified email claim.

`OIDC_SCOPES` defaults to `openid email profile`; add `groups` if your provider requires and permits that scope. `OIDC_GROUPS_CLAIM` defaults to `groups`, with nested paths such as `realm_access.roles` supported when explicitly configured. Group names are compared exactly and case-sensitively. TeslaTalk reads the verified ID token and, where available, retrieves UserInfo using the access token. UserInfo must have the same `sub` as the ID token. Group claims may come from either source. For example, Authentik must have a scope mapping that emits `groups`; Authelia generally requires the `groups` scope. Keycloak needs an appropriate group mapper or an explicitly configured role claim.

For **Pocket ID**, use `OIDC_SCOPES=openid email profile groups`, `OIDC_GROUPS_CLAIM=groups` and your actual group name in `ADMIN_GROUP` (for this installation, `admin`). Pocket ID returns actual group names, not the friendly labels shown in its administration UI. Check client **OIDC Data Preview** and your user's membership if needed. Client **Allowed User Groups** controls who may sign in and does not replace TeslaTalk's administrator check. [Pocket ID's scopes and claims](https://pocket-id.org/docs/guides/scopes-and-claims).

After updating `.env`, use `docker compose ... up -d` and start a fresh login at `/auth/admin`; use `--build` too when updating code. A denied login writes `OIDC admin access denied` with the active expected group, claim path, claim names and group count. The log omits tokens, subjects, email values and group lists. A missing claim indicates an IdP mapping or scope problem; confirm that the running container has your updated settings before changing the provider. The [German guide](START.de.md#6-administration-und-handy-einrichten) includes diagnostic commands.

The admin page at `/admin` shows instance counts, integration readiness, storage and polling settings. Configuration and secrets remain in the operator's environment; this first admin page is an operational overview. A Tesla driver login never grants administrator access.

## Storage, backup and updates

Keep the Docker data volume, `.env` and EC private keys backed up together. `APP_SECRET` encrypts stored Tesla credentials; changing it makes existing credentials unreadable. Do not rotate it by rerunning bootstrap. For a consistent simple SQLite backup, stop the application before copying its data volume, or use SQLite's backup facility. Restore ownership for UID **10001**.

```bash
git pull --ff-only
docker compose -f compose.yaml -f deploy/compose.https.yaml up -d --build
```

Use the same overlay you installed with. One FastAPI worker is intentional: the WebSocket hub and rate limiter are local to that process. Horizontal scaling and multi-instance deployments need shared presence/pubsub and a server database, and are not supported in this preview.

## Development and verification

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend pytest -q backend/tests
cd frontend
npm ci --ignore-scripts --no-audit --no-fund
npm run build
npx playwright install chromium
npm run test:e2e
```

Playwright launches an isolated demo server with test-only secrets and SQLite storage. The optional real audio test requires a reachable LiveKit instance and `TT_VOICE_TEST=true`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`. GitHub Actions starts this server and checks the production Docker build. The regular UI tests cover two-driver chat, guest expiry, private sharing, mobile layout, PWA activation/offline caching and notification consent.

For hot reload, run the backend with `APP_URL=http://localhost:5173`, an explicit `APP_SECRET`, writable `DB_PATH` and `DEMO_MODE=true`; run `npm run dev` in `frontend`. Vite proxies `/api` and `/auth`. The service worker is enabled in production builds only.
