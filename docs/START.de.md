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

`tls=true` schaltet HTTPS ein; ein gültiges Zertifikat muss Traefik zusätzlich bereitstellen. Wenn dein Traefik Zertifikate über einen ACME-Resolver anfordert, setze in `.env` `TRAEFIK_CERT_RESOLVER=DEIN_RESOLVER`. TeslaTalk übernimmt denselben Resolver für Webanwendung und Sprachserver. Der Name muss exakt einem bereits in Traefik konfigurierten Resolver entsprechen, zum Beispiel dem Resolver eines funktionierenden anderen Dienstes. Ein Eintrag in `.env` legt keinen neuen Traefik-Resolver an. Bei vorhandenen passenden Zertifikaten oder einem zentralen TLS-Standard lässt du den Wert leer. Siehe [Traefiks Zertifikatsresolver](https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/).

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
| `OIDC_SCOPES` | Standard `openid email profile`; ergänze `groups`, wenn dein Anbieter diesen Scope für Gruppen verlangt |
| `OIDC_GROUPS_CLAIM` | Standard `groups`; alternativ der genaue Claim-Pfad, etwa `realm_access.roles` |
| `ADMIN_GROUP` | Standard `teslatalk-admin`; bei dir `admin`, exakt wie vom Anbieter übermittelt |
| `ADMIN_EMAILS` | Alternativ erlaubte Admin-E-Mail-Adressen, durch Kommas getrennt; der Anbieter muss die E-Mail als verifiziert melden |
| `VAPID_SUBJECT` | `mailto:` gefolgt von deiner echten Kontaktadresse |
| `PROXY_NETWORK` | Nur ergänzen, wenn dein Netzwerk anders heißt; Standard ist `proxy` |
| `TRAEFIK_CERT_RESOLVER` | Exakter Name deines vorhandenen Zertifikatsresolvers; sonst leer lassen |

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

Der Health-Endpunkt bestätigt die laufende Anwendung. Er prüft keine echte Tesla-Anmeldung, Mikrofonverbindung oder Push-Zustellung. Für einen Sprachtest treten zwei getrennte Browserprofile einer aktuell laufenden Fahrt bei und verbinden jeweils den Funk. Einmal auf den großen Mikrofonknopf tippen schaltet das Sprechen ein, ein weiterer Tipp schaltet es aus. Der Zustand wird sichtbar angezeigt. Beim Verlassen der Seite oder Trennen wird das Mikrofon stumm. Alternativ gibt es Sprachaktivierung; mehrere Teilnehmer können gleichzeitig sprechen.

## 5. Tesla-Anmeldung freischalten

1. Lege im [Tesla-Entwicklerportal](https://developer.tesla.com/) eine Fleet-API-Anwendung an. Dein Tesla-Konto braucht eine verifizierte E-Mail und aktivierte Mehrfaktor-Authentifizierung. Gib die vom Portal verlangten Anwendungsdaten wahrheitsgemäß an; falls der Name `TeslaTalk` bereits vergeben ist, verwende einen eindeutigen Namen für deine Instanz.

   | Feld im Tesla-Portal | Wert für deine Instanz |
   | --- | --- |
   | Allowed origin / erlaubter Ursprung | `https://teslatalk.glockb.de` |
   | Redirect URI | `https://teslatalk.glockb.de/auth/tesla/callback` |
   | Region / API-Audience | Europa: `https://fleet-api.prd.eu.vn.cloud.tesla.com` |
   | Öffentlicher Schlüssel | `https://teslatalk.glockb.de/.well-known/appspecific/com.tesla.3p.public-key.pem` |

2. Konfiguriere die für V1 benötigten Konto-, Fahrzeugdaten- und Standortberechtigungen. TeslaTalk fordert `openid offline_access user_data vehicle_device_data vehicle_location` an. Setze auch ein passendes API-Budget im Tesla-Portal.
3. Trage die Zugangsdaten dieser TeslaTalk-Anwendung in die bestehende `.env` ein. Behalte alle bereits erzeugten Schlüssel:

   ```dotenv
   TESLA_CLIENT_ID=DEINE_CLIENT_ID
   TESLA_CLIENT_SECRET=DEIN_CLIENT_SECRET
   TESLA_FLEET_URL=https://fleet-api.prd.eu.vn.cloud.tesla.com
   DEMO_MODE=false
   ```

   Wende die Änderung an:

   ```bash
   docker compose -f compose.traefik.yaml up -d
   ```

4. Prüfe Konfiguration und öffentlich erreichbare Schlüsseldatei, bevor du registrierst:

   ```bash
   python3 scripts/register_tesla.py --check
   ```

   Das Skript prüft per HTTPS, ob ein gültiger öffentlicher EC-Schlüssel ausgeliefert wird und mit `deploy/keys/tesla-public-key.pem` übereinstimmt. Es verwendet Python 3 und OpenSSL auf dem Docker-Host, benötigt keine zusätzlichen Python-Pakete und ändert bei `--check` nichts bei Tesla. Die Gültigkeit deiner Client-Zugangsdaten wird erst im nächsten Schritt geprüft.

5. Registriere die Domain einmalig mit den eingetragenen Client-Zugangsdaten in der konfigurierten Fleet-Region:

   ```bash
   python3 scripts/register_tesla.py
   ```

   Das Skript fordert einen kurzlebigen Partner-Token an und sendet die Partnerregistrierung an Tesla. Es gibt weder Secret noch Token aus und speichert keinen Partner-Token. Bei Fehlern nennt es den betroffenen Schritt und HTTP-Status. `401` beim Token-Abruf deutet auf die Client-Zugangsdaten, `403` auf Anwendungsfreigabe oder Berechtigungen hin; prüfe außerdem Allowed Origin und Region. Die Einrichtung folgt Teslas [Onboarding](https://developer.tesla.com/docs/fleet-api/getting-started/what-is-fleet-api), [Partner-Token-Verfahren](https://developer.tesla.com/docs/fleet-api/authentication/partner-tokens) und [Partnerregistrierung](https://developer.tesla.com/docs/fleet-api/endpoints/partner-endpoints).

6. Melde dich auf TeslaTalk über die offizielle Tesla-Anmeldeseite an. Öffne dein Profil, rufe die Fahrzeuge ab und wähle dein Fahrzeug beziehungsweise einen Favoriten.

TeslaTalk erhält OAuth-Tokens und fragt keine Tesla-Passwörter ab. Ein laufender Container allein ersetzt die Einrichtung der Fleet-API-Anwendung nicht. Die Kopplung eines virtuellen Fahrzeugschlüssels wird später für Fahrzeugbefehle und Fleet Telemetry benötigt; die aktuelle Version ruft Konto-, Fahrzeug- und Standortdaten ab.

## 6. Administration und Handy einrichten

Für die Administration registrierst du beim OIDC-Anbieter eine eigene Anwendung mit Redirect-URI **`https://teslatalk.glockb.de/auth/admin/callback`**. Trage dessen tatsächlichen Issuer, Client-ID und Client-Secret ein. Für die Gruppe `admin` kommen diese Einstellungen hinzu:

```dotenv
ADMIN_GROUP=admin
OIDC_GROUPS_CLAIM=groups
OIDC_SCOPES=openid email profile
```

TeslaTalk prüft den signierten ID-Token und fragt zusätzlich den UserInfo-Endpunkt des Anbieters ab, wenn dieser vorhanden ist. Beide Antworten müssen dieselbe Nutzer-ID (`sub`) haben. Der konfigurierte Gruppen-Claim darf in einer dieser Antworten stehen. Der Gruppenname muss exakt passen, einschließlich Groß-/Kleinschreibung. Die Zuordnung zum OIDC-Client allein garantiert noch nicht, dass der Anbieter die Gruppe übermittelt.

- **Authelia:** Für Gruppen normalerweise `OIDC_SCOPES=openid email profile groups` setzen und den `groups`-Scope am Client erlauben.
- **Pocket ID:** Ebenfalls `OIDC_SCOPES=openid email profile groups` verwenden, `OIDC_GROUPS_CLAIM=groups` und bei dir `ADMIN_GROUP=admin`. Dein Benutzer muss Mitglied dieser Gruppe sein. Pocket ID übermittelt den tatsächlichen **Gruppennamen**, nicht den Anzeigenamen; prüfe ihn bei Bedarf mit „OIDC Data Preview“ am Client. „Allowed User Groups“ erlaubt die Client-Anmeldung und ersetzt nicht die Administratorprüfung in TeslaTalk. Siehe [Pocket-ID-Scopes und Claims](https://pocket-id.org/docs/guides/scopes-and-claims).
- **Authentik:** Eine Scope-Zuordnung muss die Gruppe im `groups`-Claim liefern. Die Gruppe kann über UserInfo kommen, auch wenn sie nicht in den ID-Token aufgenommen wird.
- **Keycloak:** Gruppen über einen Mapper als `groups` ausgeben. Für Realm-Rollen den Mapper so konfigurieren, dass die Rollen im ID-Token oder in UserInfo stehen, und `OIDC_GROUPS_CLAIM=realm_access.roles` setzen. Client-Rollen benötigen ihren tatsächlichen Claim-Pfad.

Wende `.env`-Änderungen mit `docker compose -f compose.traefik.yaml up -d` an und starte anschließend eine neue Anmeldung über `/auth/admin`. Wenn du zugleich den Code aktualisiert hast, verwende `up -d --build`. Die Administration liegt unter **https://teslatalk.glockb.de/admin** und bietet in V1 eine Statusübersicht.

Bei `Keine Administrator-Berechtigung.` prüfst du zuerst, welche Einstellungen im laufenden Container angekommen sind:

```bash
docker compose -f compose.traefik.yaml exec -T teslatalk python -c 'from app.config import settings; print("ADMIN_GROUP:", repr(settings.admin_group)); print("OIDC_GROUPS_CLAIM:", settings.oidc_groups_claim); print("OIDC_SCOPES:", settings.oidc_scopes)'
docker compose -f compose.traefik.yaml logs --tail=100 teslatalk
```

Die Fehlermeldung unterscheidet einen fehlenden Gruppen-Claim, eine leere Gruppenliste und eine fehlende Mitgliedschaft in der erlaubten Gruppe. Die Logzeile `OIDC admin access denied` nennt zusätzlich die erwartete Gruppe, den Claim-Pfad, vorhandene Claim-Namen und die Anzahl übermittelter Gruppen. `groups_present: false` bedeutet, dass der konfigurierte Claim fehlt. `group_count: 0` bedeutet, dass keine verwertbare Gruppe vorliegt. Bei einer anderen Gruppe bleibt der Zugang gesperrt. Die Diagnose enthält keine OAuth-Tokens, Nutzer-IDs, E-Mail-Adressen oder tatsächlichen Gruppenlisten. `ADMIN_EMAILS` ist eine alternative ausdrückliche Freigabe und verlangt `email_verified=true` vom Anbieter.

Für das Handy öffnest du deine TeslaTalk-Adresse und installierst die PWA über **Mein Profil → Zum Home-Bildschirm** beziehungsweise das Browser-Menü. Starte sie anschließend über das Symbol und aktiviere unter **Mein Profil → Benachrichtigungen & Web-App** ausdrücklich die Benachrichtigungen. Die Auswahl wird pro Konto und Gerät gespeichert. Ein fehlgeschlagener Serverabgleich schaltet sie nicht aus. Fehlt das Browser-Abonnement oder ist die Freigabe blockiert, zeigt das Profil den Grund und bietet die erneute Aktivierung an. Mitfahrer erhalten dieselbe Einstellung; ihr Zugang endet weiterhin mit der Fahrt. Auf iPhone/iPad erfordert Home-Screen-Web-Push mindestens iOS/iPadOS 16.4.

Über **Mein Profil → Benachrichtigungen & Web-App → Testnachricht an dieses Gerät** kannst du eine Nachricht nur an den aktuellen Browser beziehungsweise die geöffnete installierte Web-App senden. Der Button erscheint nach der Aktivierung. TeslaTalk gleicht das Browser-Abonnement zuerst ab und zeigt an, ob der Push-Dienst die Nachricht angenommen hat. Prüfe danach die Mitteilungszentrale; Fokusmodus und Systemeinstellungen können die Anzeige beeinflussen. Abgelaufene Abonnements können direkt erneut aktiviert werden. Es sind höchstens drei Tests pro Minute möglich.

In der **Administration → Testnachricht an alle Geräte** wird der Versand an alle Geräte auf diesem Server mit aktivierten Benachrichtigungen und gültiger Anmeldung eingeplant. Das umfasst auch installierte Web-Apps im Hintergrund. Mitfahrer werden nur während ihrer gültigen Fahrt berücksichtigt. Die angezeigten Zahlen nennen eingeplante Geräte und Konten; sie bestätigen keine Zustellung. Auch hier sind höchstens drei Tests pro Minute möglich.

Die mobile Seite unterbindet Seitenzoom und verwendet Eingabefelder mit mindestens 16 px, damit iOS beim Schreiben nicht automatisch vergrößert. Die Karte behält ihre eigene Zoomfunktion. Browser- und Betriebssystemhilfen können eigene Darstellungsregeln haben; die Bedienung im echten Fahrzeug und auf iOS bleibt Teil des Praxistests.

Unter **Mein Profil → Persönliche API-Schlüssel** kannst du „Ohne Ablaufdatum“ wählen. Auch diese Schlüssel sind jederzeit widerrufbar. Bei **Standort teilen** wird dein Browser-Standort als Person dargestellt, getrennt vom Fahrzeugstandort aus Fleet/Telemetrie. Mitfahrer können ebenfalls teilen. Beim Stoppen verschwindet der persönliche Live-Marker; ohne neue Daten läuft er nach fünf Minuten aus. Der private Fahrtverlauf bleibt erhalten.

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
| Zertifikatsfehler | `TRAEFIK_CERT_RESOLVER`, DNS-A/AAAA-Einträge und gültige Traefik-Zertifikate für beide Hostnamen prüfen; Details unten |
| Mikrofon/Karte bleiben gesperrt | Seite per HTTPS öffnen und Browserberechtigungen erteilen; Unterstützung im jeweiligen Tesla prüfen |
| Chat funktioniert, Sprechfunk nicht | Voice-DNS, TLS, WebSocket-Verbindung sowie Firewall/Portweiterleitung für `7881/TCP` und `7882/UDP` |
| Tesla-Anmeldung fehlt | `TESLA_CLIENT_ID`, `TESLA_CLIENT_SECRET`, Callback und Partnerregistrierung prüfen; Container nach `.env`-Änderung neu erstellen |
| OIDC-Anmeldung wird abgewiesen | Issuer/Callback sowie `groups`-Claim oder verifizierte E-Mail-Freigabe prüfen |
| Bind-Datei fehlt oder wird als Verzeichnis erkannt | Bootstrap aus Schritt 2 ausführen; öffentliche Schlüsseldatei und `deploy/livekit.yaml` müssen Dateien sein |

### HTTPS-Zertifikatfehler prüfen

Wenn `TRAEFIK DEFAULT CERT` angezeigt wird, lasse zuerst den tatsächlichen Resolvernamen und die TeslaTalk-Router prüfen:

```bash
python3 scripts/check_traefik.py
```

Der Check liest laufende Docker-Container und zeigt nur Resolvernamen, öffentliche Adressen, Netzwerkzuordnung und Zielports. Er verändert nichts und gibt keine Zugangsdaten aus. Cloudflare als DNS-Anbieter bedeutet nicht automatisch, dass dein Resolver `cloudflare` heißt. Übernimm den **exakten bereits konfigurierten** Namen in `TRAEFIK_CERT_RESOLVER`, falls du ACME nutzt; beim Zertifikats-Standard des Routers oder manuell hinterlegten Zertifikaten muss die passende Traefik-Konfiguration greifen.

Prüfe beide Domains ohne Umgehung der Zertifikatsprüfung:

```bash
curl -I https://teslatalk.glockb.de
curl -I https://teslatalk-voice.glockb.de
```

Bei einem Fehler kannst du auf dem Server das ausgelieferte Zertifikat und den Prüfgrund anzeigen:

```bash
openssl s_client -connect teslatalk.glockb.de:443 -servername teslatalk.glockb.de -verify_hostname teslatalk.glockb.de -verify_return_error </dev/null
```

- **`TRAEFIK DEFAULT CERT` oder selbst signiertes Zertifikat:** Traefik hat kein passendes vertrauenswürdiges Zertifikat für diesen Host. Prüfe den bestehenden Resolver und die ACME-Logs in Traefik.
- **Falscher Hostname:** Zertifikat, Router-Regel und DNS passen nicht zusammen. Öffne die Domain aus `APP_URL` und kontrolliere auch einen vorhandenen AAAA-Eintrag; er muss zum richtigen Server führen.
- **Abgelaufen / noch nicht gültig:** Zertifikatserneuerung sowie Datum und Uhrzeit auf dem Gerät prüfen.
- **Fehler nur auf einem Gerät oder im WLAN:** Prüfe, ob interne DNS-Einträge, ein zusätzlicher Proxy oder ein Zertifikatscache auf einen anderen Endpunkt führen.

Nach Korrektur der `.env` den Container mit `docker compose -f compose.traefik.yaml up -d` neu erstellen. Webanwendung und Voice-Domain brauchen beide gültiges HTTPS, damit Anmeldung, Mikrofon und PWA zuverlässig funktionieren.

### Mikrofon: `could not establish signal connection: Load failed`

Diese Meldung betrifft den Verbindungsaufbau zum Sprachserver. Prüfe die Konfiguration im laufenden Container; persönliche Tokens und Geheimnisse werden dabei nicht angezeigt:

```bash
python3 scripts/check_traefik.py
curl -I https://teslatalk-voice.glockb.de
docker compose -f compose.traefik.yaml logs --tail=100 livekit
```

`LIVEKIT_URL` muss **`wss://teslatalk-voice.glockb.de`** sein. Die interne Adresse `http://livekit:7880` gehört ausschließlich in `LIVEKIT_INTERNAL_URL`. Der Voice-Router muss intern auf **7880** zeigen und am Traefik-Netz hängen. Ein HTTP-Status allein beweist noch keine autorisierte Audioverbindung; entscheidend ist zunächst, dass `curl` **keinen Zertifikatsfehler** erhält. LiveKit verlangt ein vertrauenswürdiges Zertifikat; ein selbst signiertes Traefik-Standardzertifikat reicht nicht. [Offizielle LiveKit-Einrichtung](https://docs.livekit.io/transport/self-hosting/deployment/).

Bei einem aktivierten **Cloudflare-Proxy** prüfe **Network → WebSockets** und die Regeln für die Voice-Domain. Der Verbindungsaufbau darf nicht an einer zusätzlichen Login-Seite, Browser-Challenge oder WAF-Regel hängen bleiben. Cloudflare unterstützt WebSockets, prüft aber den anfänglichen Upgrade-Request mit seinen Sicherheitsregeln. Ändere nur die tatsächlich blockierende Regel; [Cloudflare-WebSocket-Diagnose](https://developers.cloudflare.com/network/websockets/). Audio benötigt zusätzlich die direkten Media-Ports aus Schritt 1; diese ersetzen keine funktionierende HTTPS-Signalisierung.

### Mac zeigt die Offline-Seite, iPhone zeigt die Anwendung

Die Offline-Seite bedeutet, dass **dieser Browser** TeslaTalk nicht erreicht. Neben einer fehlenden Internetverbindung können TLS, unterschiedliche DNS-Wege oder lokale Browserdaten die Ursache sein. Nach dem Update prüft „Erneut verbinden“ den Serverstatus; die Seite kehrt bei wiederhergestellter Verbindung automatisch zurück. CSS und Icons funktionieren nun auch offline.

Falls das Problem nach gültigem HTTPS bestehen bleibt: Öffne die Seite am Mac in einem privaten Safari-Fenster (**⇧⌘N**). Funktioniert sie dort, entferne nur die Daten dieser Website unter **Safari → Einstellungen → Datenschutz → Websitedaten verwalten** und melde dich erneut an. Dadurch werden auch lokale Geräteeinstellungen zurückgesetzt; Benachrichtigungen anschließend im Profil erneut prüfen. [Apple-Anleitung](https://support.apple.com/de-de/102564).

### iPhone zeigt nur ein „t“ als Home-Bildschirm-Icon

Ein undurchsichtiges 180×180-PNG ist unter dem neuen Dateinamen `/apple-touch-icon-v4.png` eingebunden und zusätzlich unter `/apple-touch-icon.png` sowie `/apple-touch-icon-precomposed.png` verfügbar. Öffne bei gültigem HTTPS `https://teslatalk.glockb.de/apple-touch-icon-v4.png`; dort muss das rote TeslaTalk-Icon erscheinen. Die Installationshilfe zeigt eine Vorschau. Entferne anschließend den alten Home-Bildschirm-Eintrag, öffne die TeslaTalk-Startseite in Safari und füge sie erneut hinzu. Bereits gespeicherte iOS-Symbole werden durch das Server-Update nicht zuverlässig ersetzt. Prüfe und aktiviere Benachrichtigungen danach wieder im persönlichen Profil.

Weitere Details: [allgemeine Einrichtung](SETUP.md) · [API](API.md) · [Projektübersicht](../README.md).
