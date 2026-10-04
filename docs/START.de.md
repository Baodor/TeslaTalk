# TeslaTalk starten: Docker Compose mit Traefik

Diese Anleitung richtet TeslaTalk unter **https://teslatalk.glockb.de** mit deinem vorhandenen Traefik und dem Docker-Netzwerk **proxy** ein. Für den Sprechfunk wird zusätzlich **teslatalk-voice.glockb.de** verwendet.

Die vollständige [compose.traefik.yaml](../compose.traefik.yaml) enthält die Webanwendung samt API, den LiveKit-Sprachserver, einen persistenten Datenspeicher und beide Traefik-Router. Du verwendest sie **allein**, ohne eine zweite Compose-Datei. TeslaTalk nutzt SQLite; ein zusätzlicher Datenbankcontainer ist für diese Version nicht erforderlich.

TeslaTalk 0.1 ist eine Preview. Die Weboberfläche kann jetzt gestartet werden; echte Tesla-Anmeldung und Fahrzeugdaten brauchen deine eigene Tesla-Fleet-Anwendung. Ladeplanung, Routenabgleich und Immich folgen später und sind für den Start nicht erforderlich. Tests im echten Fahrzeug und Push-Zustellung auf physischen Handys stehen noch aus.

## 1. Server, DNS und Traefik vorbereiten

Du brauchst **Git, Python 3, OpenSSL und Docker mit Compose v2** auf dem Docker-Host. Docker muss für deinen Benutzer nutzbar sein.

| Einstellung | Wert |
| --- | --- |
| DNS für die Webanwendung | `teslatalk.glockb.de` → öffentliche IP deines Servers |
| DNS für den Sprachserver | `teslatalk-voice.glockb.de` → dieselbe öffentliche IP |
| Traefik-Entrypoint | `websecure` |
| Externes Docker-Netzwerk | `proxy`; Traefik muss ebenfalls damit verbunden sein |
| TLS | Gültige Zertifikate für beide Hostnamen in deinem vorhandenen Traefik |

Prüfe Docker, Compose und das Netzwerk:

```bash
docker version
docker compose version
docker network inspect proxy
```

Die Compose-Datei übernimmt deine Labels mit `tls=true` und der ausdrücklichen Service-Zuordnung. Der Zielport für TeslaTalk lautet **8780**, weil die Anwendung dort im Container lauscht. LiveKit lauscht intern auf **7880**. Beide Ports werden in dieser Konfiguration über das Docker-Netzwerk erreicht und nicht am Host veröffentlicht.

Ein Zertifikatsresolver ist nicht fest vorgegeben. Falls dein Traefik neue Zertifikate nur mit einem Router-Label anfordert, ergänze bei beiden Services `traefik.http.routers.teslatalk.tls.certresolver=DEIN_RESOLVER` beziehungsweise `traefik.http.routers.teslatalk-voice.tls.certresolver=DEIN_RESOLVER` mit dem Namen aus deiner bestehenden Traefik-Konfiguration.

### Ports für den Sprechfunk

| Port am Host | Zweck | Erreichbarkeit |
| --- | --- | --- |
| `443/TCP` | Webanwendung und Sprach-Signalisierung über Traefik | Bereits über deinen Traefik |
| `7881/TCP` | Direkte WebRTC-Verbindung als TCP-Fallback | Firewall und gegebenenfalls Router zum Docker-Host freigeben |
| `7882/UDP` | Direkte WebRTC-Audiodaten | Firewall und gegebenenfalls Router zum Docker-Host freigeben |

Traefik übernimmt HTTPS und WebSockets. Die Audiodaten benötigen zusätzlich die direkten Media-Ports. Bei einem Server hinter einem Router leitest du **7881/TCP** und **7882/UDP** auf dieselben Ports des Docker-Hosts weiter. Für Netze, die diese Verbindungen blockieren, kann ein zusätzlicher TURN-Server nötig werden; dieser ist in der Standardkonfiguration nicht enthalten. Die Zuordnung entspricht den [offiziellen LiveKit-Portanforderungen](https://docs.livekit.io/transport/self-hosting/ports-firewall/).

## 2. Projekt herunterladen und Schlüssel erzeugen

Auf einer **neuen Installation**:

```bash
git clone https://github.com/Baodor/TeslaTalk.git
cd TeslaTalk
python3 scripts/configure.py \
  --url https://teslatalk.glockb.de \
  --voice-url wss://teslatalk-voice.glockb.de \
  --email du@example.com
```

Ersetze `du@example.com` durch deine echte Kontaktadresse für Web Push. Der Befehl erzeugt automatisch:

- `.env`: Einstellungen, Anwendungsschlüssel und Zugangsdaten für LiveKit.
- `deploy/livekit.yaml`: passende Konfiguration des Sprachservers mit denselben Zugangsdaten.
- `deploy/keys/`: VAPID-Schlüssel für Benachrichtigungen und das Tesla-Schlüsselpaar.

Die geheimen Dateien werden nicht in Git gespeichert. In den Webcontainer wird nur der **öffentliche** Tesla-Schlüssel eingebunden.

**Wenn bereits eine `.env` vorhanden ist:** Führe die Schlüsselerzeugung nicht erneut aus. Das Skript verweigert das Überschreiben. Passe die vorhandenen Werte wie in Schritt 3 an und behalte `APP_SECRET`, die VAPID-Schlüssel sowie die zusammengehörigen LiveKit-Schlüssel. Wenn du von der bisherigen Compose-Konfiguration wechselst, benutze denselben Projektordner und gegebenenfalls denselben bisherigen `-p`-Projektnamen, damit das vorhandene Datenvolume weiterverwendet wird.

## 3. Deine Einstellungen eintragen

```bash
nano .env
```

Für diese Installation müssen die Adressen so lauten; auf einer neuen Installation hat das Skript sie bereits gesetzt:

```dotenv
APP_URL=https://teslatalk.glockb.de
APP_HOST=teslatalk.glockb.de
APP_TIMEZONE=Europe/Berlin
LIVEKIT_URL=wss://teslatalk-voice.glockb.de
VOICE_HOST=teslatalk-voice.glockb.de
DEMO_MODE=false
```

Die weiteren Angaben ergänzt du in derselben `.env`. Trage dort die tatsächlichen Werte ein, ohne die erzeugten Schlüssel zu ersetzen:

| Variable | Was du einträgst |
| --- | --- |
| `TESLA_CLIENT_ID` | Client-ID deiner Anwendung aus dem Tesla-Entwicklerportal |
| `TESLA_CLIENT_SECRET` | Client-Secret dieser Anwendung |
| `TESLA_FLEET_URL` | Für Europa bereits auf `https://fleet-api.prd.eu.vn.cloud.tesla.com` gesetzt |
| `FLEET_POLL_INTERVAL` | Standard `120`: Sekunden zwischen Fahrzeugabfragen während aktiver Fahrten |
| `OIDC_ISSUER` | Issuer-URL deines OIDC-Anbieters für die Administration; optional beim ersten Start |
| `OIDC_CLIENT_ID` | Client-ID der separaten Administrator-Anwendung |
| `OIDC_CLIENT_SECRET` | Deren Client-Secret |
| `ADMIN_GROUP` | Standard `teslatalk-admin`; diese Gruppe muss im ID-Token enthalten sein |
| `ADMIN_EMAILS` | Alternativ erlaubte Admin-E-Mail-Adressen, durch Kommas getrennt; der Anbieter muss die E-Mail als verifiziert melden |
| `VAPID_SUBJECT` | `mailto:` gefolgt von deiner echten Kontaktadresse |
| `PROXY_NETWORK` | Nur ergänzen, wenn dein Netzwerk anders heißt; Standard ist `proxy` |

`APP_SECRET`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `VAPID_PRIVATE_KEY` und `VAPID_PUBLIC_KEY` werden automatisch erzeugt. Du brauchst für Web Push keinen weiteren Container.

Du kannst den Server zunächst ohne Tesla- und OIDC-Zugangsdaten starten und seine Erreichbarkeit prüfen. Für den Fahrer-Login brauchst du anschließend Schritt 5. Wenn du vorher die Oberfläche ausprobieren möchtest, setze vorübergehend `DEMO_MODE=true`. Dieser Modus verwendet Beispieldaten und einen Demo-Login; stelle für echte Fahrzeuge wieder auf `false` um.

## 4. Container bauen und starten

Alle folgenden Befehle führst du im Projektordner aus:

```bash
docker compose -f compose.traefik.yaml config --quiet
docker compose -f compose.traefik.yaml up -d --build
docker compose -f compose.traefik.yaml ps
```

Der erste Build lädt die Abhängigkeiten und baut Frontend und Backend. Öffne anschließend **https://teslatalk.glockb.de**. Den Serverzustand prüfst du mit:

```bash
curl -fsS https://teslatalk.glockb.de/api/health
docker compose -f compose.traefik.yaml logs --tail=100 teslatalk livekit
```

Der Health-Endpunkt bestätigt die laufende Anwendung. Er prüft keine echte Tesla-Anmeldung, Mikrofonverbindung oder Push-Zustellung. Für einen Sprachtest treten zwei getrennte Browserprofile einer aktuell laufenden Fahrt bei, aktivieren jeweils das Mikrofon und sprechen miteinander.

## 5. Tesla-Anmeldung freischalten

1. Lege im [Tesla-Entwicklerportal](https://developer.tesla.com/) eine Fleet-API-Anwendung an. Hinterlege als erlaubten Ursprung `https://teslatalk.glockb.de` und als exakte Redirect-URI **`https://teslatalk.glockb.de/auth/tesla/callback`**.
2. Konfiguriere die für V1 benötigten Konto-, Fahrzeugdaten- und Standortberechtigungen. TeslaTalk fordert `openid offline_access user_data vehicle_device_data vehicle_location` an. Setze auch ein passendes API-Budget im Tesla-Portal.
3. Trage `TESLA_CLIENT_ID` und `TESLA_CLIENT_SECRET` in `.env` ein und wende die Änderung an:

   ```bash
   docker compose -f compose.traefik.yaml up -d
   ```

4. Prüfe die öffentlich erreichbare Schlüsseldatei:

   ```bash
   curl -fsS https://teslatalk.glockb.de/.well-known/appspecific/com.tesla.3p.public-key.pem
   ```

5. Registriere die Domain mit den eingetragenen Client-Zugangsdaten in der konfigurierten Fleet-Region:

   ```bash
   python3 scripts/register_tesla.py
   ```

   Das Skript sendet die Partnerregistrierung an Tesla. Die Schritte und Berechtigungen richten sich nach Teslas [Partnerregistrierung](https://developer.tesla.com/docs/fleet-api/endpoints/partner-endpoints); abweichende Anforderungen deiner Anwendung stehen im Entwicklerportal.

6. Melde dich auf TeslaTalk über die offizielle Tesla-Anmeldeseite an. Öffne dein Profil, rufe die Fahrzeuge ab und wähle dein Fahrzeug beziehungsweise einen Favoriten.

TeslaTalk erhält OAuth-Tokens und fragt keine Tesla-Passwörter ab. Ein laufender Container allein ersetzt die Einrichtung der Fleet-API-Anwendung nicht.

## 6. Administration und Handy einrichten

Für die Administration registrierst du beim OIDC-Anbieter eine eigene Anwendung mit Redirect-URI **`https://teslatalk.glockb.de/auth/admin/callback`**. Setze die drei `OIDC_*`-Variablen sowie die Gruppe oder E-Mail-Freigabe in `.env`. Wende Änderungen mit `docker compose -f compose.traefik.yaml up -d` an. Die Administration liegt unter **https://teslatalk.glockb.de/admin** und bietet in V1 eine Statusübersicht.

Für das Handy öffnest du deine TeslaTalk-Adresse und installierst die PWA über **Zum Home-Bildschirm** beziehungsweise **App installieren**. Starte sie anschließend über das Symbol und aktiviere in TeslaTalk ausdrücklich die Benachrichtigungen. Auf iPhone/iPad erfordert Home-Screen-Web-Push mindestens iOS/iPadOS 16.4. Die [ausführliche Anleitung](SETUP.md#home-screen-installation-and-notifications) erklärt Geräteunterstützung und die noch ausstehenden Praxistests.

## Updates, Neustart und Sicherung

Nach Änderungen an `.env` verwende `up -d`, damit Compose den Container mit den neuen Umgebungsvariablen neu erstellt. Ein bloßes `restart` lädt diese Änderungen nicht neu.

```bash
git pull --ff-only
docker compose -f compose.traefik.yaml up -d --build
```

Fahrten, Konten und Chat liegen im Volume `teslatalk-data`; der tatsächliche Docker-Name bekommt den Compose-Projektnamen als Präfix. Sichere dieses Volume zusammen mit `.env`, `deploy/livekit.yaml` und `deploy/keys/`. Für eine einfache konsistente Datenbanksicherung stoppe TeslaTalk während des Kopierens. Beim Wiederherstellen benötigt die Anwendung Schreibrechte für UID **10001**. `docker compose down` behält das Volume; **`down -v` löscht es**.

## Wenn etwas nicht funktioniert

| Symptom | Prüfen |
| --- | --- |
| Traefik meldet `502` | Beide Container und Traefik sind am selben `proxy`-Netzwerk; Zielports sind `8780` und `7880` |
| Zertifikatsfehler | DNS und gültiges Traefik-Zertifikat für beide Hostnamen; gegebenenfalls deinen vorhandenen Resolver ergänzen |
| Mikrofon/Karte bleiben gesperrt | Seite per HTTPS öffnen und Browserberechtigungen erteilen; Unterstützung im jeweiligen Tesla prüfen |
| Chat funktioniert, Sprechfunk nicht | Voice-DNS, TLS, WebSocket-Verbindung sowie Firewall/Portweiterleitung für `7881/TCP` und `7882/UDP` |
| Tesla-Anmeldung fehlt | `TESLA_CLIENT_ID`, `TESLA_CLIENT_SECRET`, Callback und Partnerregistrierung prüfen; Container nach `.env`-Änderung neu erstellen |
| OIDC-Anmeldung wird abgewiesen | Issuer/Callback sowie `groups`-Claim oder verifizierte E-Mail-Freigabe prüfen |
| Bind-Datei fehlt oder wird als Verzeichnis erkannt | Bootstrap aus Schritt 2 ausführen; öffentliche Schlüsseldatei und `deploy/livekit.yaml` müssen Dateien sein |

Weitere Details: [allgemeine Einrichtung](SETUP.md) · [API](API.md) · [Projektübersicht](../README.md).
