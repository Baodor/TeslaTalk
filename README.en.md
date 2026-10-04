<div align="center">

# TeslaTalk

### Travel together. Stay connected.

<a href="README.md"><img alt="Read in German" src="https://img.shields.io/badge/Read_in-Deutsch-8eefbb?style=for-the-badge&labelColor=101a20"></a>

**Voice radio · Trips · Live map · Friends · Road trips**

![License](https://img.shields.io/badge/License-AGPLv3-8eefbb?style=flat-square&labelColor=101a20)
![Self hosted](https://img.shields.io/badge/Self--Hosted-Docker-8eefbb?style=flat-square&labelColor=101a20)
![Status](https://img.shields.io/badge/Status-V1_in_development-f5c76d?style=flat-square&labelColor=101a20)

Your group. Your trip. Your server.

</div>

---

TeslaTalk connects friends travelling together in their Teslas. Each trip brings voice radio, chat and a participant map into one place. The interface is designed for the Tesla browser and also works on phones, tablets and computers. Run your own server in Docker.

> The initial implementation is currently being developed. This overview distinguishes the agreed first release from later additions. Vehicle features use Tesla's official interfaces. TeslaTalk is an independent project.

## First release

| Area | Scope for V1 |
| --- | --- |
| Tesla sign-in | Official OAuth redirect; TeslaTalk never collects Tesla passwords |
| Vehicles | Retrieve account vehicles, select a vehicle and set a favourite |
| Friends | Requests, acceptance and invitations using a username, licence plate or existing email address |
| Trips | Name, destination, start and end dates; join using a PIN or invitation |
| Map | Location and vehicle data shared exclusively within your own trip |
| Voice radio | Multiple simultaneous speakers; push-to-talk and voice activation; self-hosted LiveKit server |
| Chat | Persistent trip chat, also usable from the future mobile app |
| Passengers | Personal name and PIN, QR entry without a Tesla account, valid only during the trip |
| History | Full storage of captured data and export; rankings for consumption, time and average speed |
| Administration | Separate administrator sign-in through OIDC |
| API | Foundation for future apps and personal API keys |

## Roadmap

### Shared routes and charging stops

- Adopt the trip leader's route and send it to every vehicle.
- Account for different battery levels so that the group can charge at the same Superchargers.
- Notify participants when a change is needed, then automatically update the shared route for everyone.
- Verify Tesla interfaces for route adoption, waypoints and music control with a real vehicle.

### Photo albums with Immich

- Use the **trip leader's Immich instance**.
- Automatically create an album named after the **trip and its date range**.
- Show a passenger QR code next to the photo section.
- Passengers sign in with their **name and personal PIN**; no Tesla account is required.
- Limit passenger access and photo uploads to the scheduled trip period. **Uploads are disabled after the trip ends.**
- After the trip, create a separate, revocable **read-only link** that lets external visitors view the trip overview and album.
- Public links never grant access to private chat, Tesla accounts or live locations.

### iOS and Android apps

- Configure your own server address.
- Use trips, vehicle data, the map, voice radio and chat on the go.
- Support passenger access via QR code.

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

Setup instructions, screenshots, API documentation and verified limitations will accompany the runnable first release.

## Licence

TeslaTalk is licensed under the [GNU Affero General Public License v3.0](LICENSE). Modified versions offered as a network service must make their corresponding source code available to users.

TeslaTalk is not affiliated with, endorsed or supported by Tesla, Inc. Tesla and vehicle names are trademarks of their respective owners.
