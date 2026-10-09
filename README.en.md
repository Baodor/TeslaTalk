<div align="center">

# TeslaTalk

<img src="frontend/public/favicon.svg" alt="TeslaTalk: Tesla T and walkie-talkie" width="88">

### Travel together. Stay connected.

<a href="README.md"><img alt="Read in German" src="https://img.shields.io/badge/Read_in-Deutsch-ff6b72?style=for-the-badge&labelColor=101a20"></a>

**Voice radio · Trips · Live map · Friends · Installable PWA**

![License](https://img.shields.io/badge/License-AGPLv3-ff6b72?style=flat-square&labelColor=101a20)
![Self hosted](https://img.shields.io/badge/Self--Hosted-Docker-ff6b72?style=flat-square&labelColor=101a20)
![Status](https://img.shields.io/badge/Status-0.1_Preview-f5c76d?style=flat-square&labelColor=101a20)

Your group. Your trip. Your server.

</div>

---

TeslaTalk connects friends travelling together in their Teslas. Each trip brings voice radio, chat and a participant map into one place. The interface is designed for the Tesla browser and also works on phones, tablets and computers. Run your own server in Docker. Install TeslaTalk on your phone’s **home screen**, with its own icon and **Web Push notifications**.

> **0.1 preview:** The web interface, API and demo are implemented. Real vehicles require a configured Tesla Fleet application and a reachable LiveKit server. Testing inside a real Tesla and delivery of notifications on physical phones are still pending.

![TeslaTalk – trips, map and voice radio](docs/assets/desktop.png)

*Interface in demo mode. Vehicle values shown are sample data.*

## Included in version 0.1

| Area | Implemented scope |
| --- | --- |
| Tesla sign-in | Official OAuth redirect; TeslaTalk never collects Tesla passwords |
| Vehicles | Retrieve account vehicles, select a vehicle and set a favourite |
| Friends | Requests, acceptance and invitations using a username, licence plate or existing email address |
| Trips | Name, destination, start and end dates; join using a PIN or invitation |
| Map | Personal browser-location markers with Tesla profile photos and separate vehicle markers; passengers can share their own location too |
| Voice radio | Multiple simultaneous speakers; tap to toggle your microphone and voice activation; self-hosted LiveKit server |
| Chat | Persistent trip chat with real-time updates, including the mobile PWA |
| PWA & Push | Home-screen installation; remembered notification preferences in your personal profile |
| Passengers | Personal name and PIN, QR entry without a Tesla account, valid only during the trip |
| History | Full storage of captured data and export; rankings for consumption, time and average speed |
| Administration | Separate administrator sign-in through OIDC |
| API | Documented endpoints and personal, revocable API keys, optionally without expiration |
| Sharing | Separate, revocable read-only trip summary link after a trip; album access follows with Immich |

## Phone and browser language

TeslaTalk automatically detects German, English and Dutch from the browser’s preferred languages, including regional variants such as `de-CH`, `en-US` and `nl-BE`. The first supported preference wins; English is the fallback.

**My profile → Language** offers **Automatic · Deutsch · English · Nederlands**, including for passengers. The Automatic option displays the detected phone language. A manual choice is remembered on that device after reloading; **Automatic** restores detection. Switching takes effect immediately. Other open tabs follow the choice without resetting their form input, chat drafts or an active radio connection. If browser storage is unavailable, the choice lasts for the current session.

Dates, application messages and offline recovery use the selected language. With notifications enabled, the device language is synchronised to the server; personal tests and group notifications are translated per device. A closed device uses its last synchronised language until the app is reopened. Names, destinations, chat text and technical API identifiers remain intact.

**Post-update checklist:**

- [ ] Open German, English and Dutch browser profiles without a saved override and check detection.
- [ ] Select each language in My profile → Language, reload, then restore Automatic.
- [ ] Switch through settings in a second tab while a form is open and verify input, PIN and trip selection remain intact.
- [ ] Check sign-in, QR passengers, profile, route planning, vehicle controls and administration.
- [ ] Switch through settings in a second tab during a radio connection and verify listening and microphone state are preserved.
- [ ] Send a personal push test after switching and check its language on the phone.
- [ ] Check language switching under Settings on the offline page without a connection.

## Roadmap

### Shared routes and charging stops

- Adopt the trip leader's route and send it to every vehicle.
- Account for different battery levels so that the group can charge at the same Superchargers.
- **Live availability at charging stops:** show how many charging points at planned stops are available or occupied, with the last update time. This requires live data from the respective operator.
- Notify participants when a change is needed, then automatically update the shared route for everyone.
- Verify Tesla interfaces for route adoption, waypoints and music control with a real vehicle.

### Photo albums with Immich (planned)

**Not implemented yet:** TeslaTalk currently generates only the planned album name. There is no Immich API connection, Immich credential storage or photo upload endpoint. Passenger access and public trip summaries work independently of this planned integration.

- Use the **trip leader's Immich instance**.
- Automatically create an album named after the **trip and its date range**.
- Show a passenger QR code next to the photo section.
- Passengers sign in with their **name and personal PIN**; no Tesla account is required.
- Limit passenger access and photo uploads to the scheduled trip period. **Uploads are disabled after the trip ends.**
- After the trip, create a separate, revocable **read-only link** that lets external visitors view the trip overview and album.
- Public links never grant access to private chat, Tesla accounts or live locations.

### Mobile PWA development

TeslaTalk starts as a website that can be installed on the home screen. Open your own server address; an App Store app is not needed.

- Continue testing mobile controls and notifications on real devices.
- Integrate shared charging stops and Immich into the PWA.
- Make changing servers easier directly in the interface later.

#### Idea: “I need a toilet break” 🚻

A button in the app tells the **trip leader** which participant needs a toilet break. The leader can find and select a suitable **rest area on the map**. TeslaTalk adds it as a shared waypoint and **updates the route for every participant**.

The notification is a request for a break. The leader chooses the rest area. Multiple requests could later be combined into one shared stop.

## Technical direction

| Component | Role |
| --- | --- |
| React / TypeScript | Responsive interface for the Tesla browser and mobile devices |
| FastAPI | Authentication, trips, friends, chat, vehicle data and API |
| SQLite | Persistent storage in a Docker volume |
| WebSocket | Chat, presence and location updates within each trip |
| LiveKit | Self-hosted voice radio with multiple simultaneous speakers |
| Tesla Fleet API | Official account and vehicle integration |
| OIDC | Separate administrator sign-in |

## Try it

Requirements: Git, Python 3, OpenSSL and Docker Compose v2.

```bash
git clone https://github.com/Baodor/TeslaTalk.git
cd TeslaTalk
python3 scripts/configure.py --demo
docker compose up -d --build
```

Open **http://localhost:8780**. The explicitly enabled demo mode creates sample data and requires no Tesla account. Keep `DEMO_MODE=false` for a real installation.

For HTTPS on a new installation:

```bash
python3 scripts/configure.py \
  --url https://talk.example.com \
  --voice-url wss://voice.example.com \
  --email you@example.com
docker compose -f compose.yaml -f deploy/compose.https.yaml up -d --build
```

Bootstrap does not overwrite an existing `.env`. On an existing installation, edit the addresses directly and keep the current keys.

### Start behind an existing Traefik

The complete [compose.traefik.yaml](compose.traefik.yaml) includes TeslaTalk, the LiveKit voice server, persistent storage and both routers on your external `proxy` network. Follow the [English Traefik setup](docs/SETUP.md#existing-traefik) or the [German step-by-step guide](docs/START.de.md) for `teslatalk.glockb.de`, including key generation, DNS, ports, Tesla sign-in, OIDC and PWA notifications. Once configured, start with:

```bash
docker compose -f compose.traefik.yaml up -d --build
```

Traefik connects to TeslaTalk on internal port **8780** and LiveKit on **7880**. Audio also requires directly reachable **7881/TCP** and **7882/UDP**. The existing files under `deploy/` remain overlays for `compose.yaml`.

[Setup, Tesla Fleet API, OIDC and backup](docs/SETUP.md) · [API documentation](docs/API.md)

## Voice networking ports

| Port | Purpose | Exposure |
| --- | --- | --- |
| **443/TCP** | Website and LiveKit signalling over HTTPS/WebSocket | Public through the existing HTTPS proxy |
| **7882/UDP** | Direct WebRTC audio media | Forward publicly all the way to the LiveKit container |
| **7881/TCP** | Direct WebRTC fallback when UDP is unavailable | Forward publicly all the way to the LiveKit container |
| 7880/TCP | Internal LiveKit HTTP/API | Only for TeslaTalk and the HTTPS proxy; do not expose directly |
| 8780/TCP | Internal TeslaTalk HTTP | Traefik forwards website requests here |

**CGNAT with a VPS and WireGuard:** Forward **7882/UDP and 7881/TCP** on the public VPS to the same ports on the home server's WireGuard address, allow forwarding and ensure that replies use the tunnel. A working HTTPS endpoint or outbound VPN tunnel alone does not provide this reachability.

Set `LIVEKIT_PUBLIC_IP` in `.env` to the **public VPS IPv4**, run `python3 scripts/configure_voice.py` and recreate LiveKit. The ordinary Cloudflare HTTPS proxy does not replace direct forwarding of the audio ports. This configuration uses UDP mux on 7882, so it does not require an additional 50000–60000 UDP range.

The [CGNAT guide (German)](docs/CGNAT.de.md) includes diagnostics, persistent VPS forwarding and a mobile-network audio test. The [startup guide (German)](docs/START.de.md) covers the complete Docker/Traefik setup.

## Add to the home screen

**iPhone/iPad:** Open in Safari → Share → **Add to Home Screen**. Launch from the new icon, then enable notifications under **Mein Profil → Benachrichtigungen & Web-App** (personal profile). Web Push requires iOS/iPadOS 16.4 or newer here. [Apple/WebKit explains support](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/).

**Android/Chrome:** Use the install button or browser menu, then explicitly allow notifications. The icon combines a **Tesla T with a walkie-talkie**. Installation and Push require HTTPS; the local `localhost` demo is the development exception.

Notifications never reveal chat contents, plates or location. Passengers receive Push only while their access is valid. An offline page explains connection problems; voice radio and current data require internet. Continuous background audio depends on the device and browser.

## Verified so far

- **Backend tests:** Trip access, PINs, scheduled boundaries, private sharing, OAuth state, API keys, rankings, push subscriptions, OIDC groups and Tesla registration.
- **Browser tests:** Real-time chat with two drivers, passenger entry and trip expiry, mobile layout, service workers, offline caching, notification consent, microphone permissions and profile photos on the map.
- **TypeScript and the production build** pass. GitHub Actions also verifies concurrent microphones with tap controls and builds and starts the production container.

Server Push delivery is tested with mocked push services; the browser consent test uses a mocked subscription. Real Tesla sign-in and end-to-end delivery on iOS/Android have not yet been confirmed here.

## Known limitations

- Vehicle polling runs every **120 seconds** by default for connected drivers in active trips. Personal browser location is sent at most once every ten seconds while sharing is enabled. This is not Fleet Telemetry streaming and may incur Tesla API charges.
- Consumption requires measured energy and odometer counters from a suitable integration. V1 does not estimate consumption from battery percentage.
- Charging planning, synchronized routes, music control and Immich are **roadmap features**. QR guest access works already; photo uploads are not connected yet.
- Microphone and browser availability while driving must be verified for the vehicle, region and firmware. V1 sends no vehicle commands.
- The initial admin page is an operational overview. Server configuration uses environment variables.
- One server runs one FastAPI process with SQLite. Multiple instances and distributed scaling come later.

## Licence

TeslaTalk is licensed under the [GNU Affero General Public License v3.0](LICENSE). Modified versions offered as a network service must make their corresponding source code available to users.

TeslaTalk is not affiliated with, endorsed or supported by Tesla, Inc. Tesla and vehicle names are trademarks of their respective owners.
