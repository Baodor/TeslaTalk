<div align="center">

# TeslaTalk

<img src="frontend/public/favicon.svg" alt="TeslaTalk: Tesla-T und Walkie-Talkie" width="88">

### Gemeinsam unterwegs. Verbunden bleiben.

<a href="README.en.md"><img alt="Read in English" src="https://img.shields.io/badge/Read_in-English-8eefbb?style=for-the-badge&labelColor=101a20"></a>

**Sprachfunk · Fahrten · Live-Karte · Freunde · Installierbare PWA**

![License](https://img.shields.io/badge/Lizenz-AGPLv3-8eefbb?style=flat-square&labelColor=101a20)
![Self hosted](https://img.shields.io/badge/Self--Hosted-Docker-8eefbb?style=flat-square&labelColor=101a20)
![Status](https://img.shields.io/badge/Status-0.1_Preview-f5c76d?style=flat-square&labelColor=101a20)

Deine Gruppe. Deine Fahrt. Dein Server.

</div>

---

TeslaTalk verbindet Freunde, die gemeinsam mit ihren Teslas unterwegs sind. Eine Fahrt bündelt Sprachfunk, Chat und eine Karte der Teilnehmer. Die Oberfläche ist für den Tesla-Browser gedacht und funktioniert auch auf Handy, Tablet und Computer. Der Server läuft selbst gehostet in Docker. Auf dem Handy lässt sich TeslaTalk direkt auf den **Home-Bildschirm** legen – mit eigenem Icon und **Web-Push-Benachrichtigungen**.

> **0.1 Preview:** Weboberfläche, API und Demo sind implementiert. Für echte Fahrzeuge braucht deine Installation eine konfigurierte Tesla-Fleet-Anwendung und einen erreichbaren LiveKit-Server. Tests im echten Tesla sowie die Push-Zustellung auf physischen Handys stehen noch aus.

![TeslaTalk – Fahrten, Karte und Sprechfunk](docs/assets/desktop.png)

*Die Oberfläche im Demo-Modus. Angezeigte Fahrzeugwerte sind Beispieldaten.*

## Das steckt in Version 0.1

| Bereich | Implementierter Umfang |
| --- | --- |
| Tesla-Anmeldung | Offizielle OAuth-Weiterleitung; TeslaTalk nimmt keine Tesla-Passwörter entgegen |
| Fahrzeuge | Fahrzeuge des Kontos abrufen, Fahrzeug auswählen und Favoriten festlegen |
| Freunde | Anfragen, Annahme und Einladungen über Benutzername, Kennzeichen oder vorhandene E-Mail-Adresse |
| Fahrten | Name, Ziel, Beginn und Ende; Beitritt per PIN oder Einladung |
| Karte | Standort und Fahrzeugdaten ausschließlich innerhalb der eigenen Fahrt |
| Sprachfunk | Mehrere Sprecher gleichzeitig; Push-to-Talk und Sprachaktivierung; selbst gehosteter LiveKit-Server |
| Chat | Persistenter Fahrt-Chat mit Echtzeit-Updates, auch in der mobilen PWA |
| PWA & Push | Installation auf dem Home-Bildschirm; Benachrichtigungen für Chat, Fahrteinladungen und Freundschaftsanfragen |
| Mitfahrer | Persönlicher Name und PIN, QR-Beitritt ohne Tesla-Konto, auf den Fahrtzeitraum begrenzt |
| Historie | Vollständige Speicherung der erfassten Daten und Export; Rankings für Verbrauch, Zeit und Durchschnittstempo |
| Administration | Separater Administratorzugang über OIDC |
| API | Dokumentierte Endpunkte und persönliche, widerrufbare API-Schlüssel |
| Teilen | Separater, widerrufbarer Leselink zur Fahrtübersicht nach Fahrtende; Albumzugriff folgt mit Immich |

## Roadmap

### Gemeinsame Routen und Ladestopps

- Die Route des Fahrtleiters übernehmen und an alle Fahrzeuge übertragen.
- Unterschiedliche Akkustände berücksichtigen, damit die Gruppe an denselben Superchargern laden kann.
- Auf nötige Änderungen hinweisen und danach die gemeinsame Route automatisch bei allen anpassen.
- Tesla-Schnittstellen für Routenübernahme, Zwischenstopps und Musiksteuerung am echten Fahrzeug prüfen.

### Fotoalben mit Immich

- Die Immich-Instanz des Fahrtleiters verwenden.
- Automatisch ein Album mit **Fahrtname und Zeitraum** anlegen.
- Neben dem Fotobereich einen QR-Code für benannte Mitfahrer anzeigen.
- Mitfahrer melden sich mit **Name und persönlichem PIN** an; ein Tesla-Konto ist dafür nicht erforderlich.
- Zugang und Bild-Uploads auf den eingegebenen Fahrtzeitraum begrenzen. **Nach Fahrtende sind Uploads gesperrt.**
- Nach der Fahrt einen separaten, widerrufbaren **Leselink** erstellen, über den auch externe Personen die Fahrtübersicht und das Album anschauen können.
- Öffentliche Freigaben erhalten keinen Zugang zu privaten Chats, Tesla-Konten oder Live-Standorten.

### Mobile Weiterentwicklung der PWA

TeslaTalk wird zunächst als Website umgesetzt, die sich auf dem Home-Bildschirm installieren lässt. Du öffnest die Adresse deines eigenen Servers; eine App-Store-App ist dafür nicht nötig.

- Die mobile Bedienung und Benachrichtigungen auf echten Geräten weiter prüfen.
- Gemeinsame Ladestopps und Immich in die PWA integrieren.
- Einen Serverwechsel direkt in der Oberfläche später erleichtern.

#### Idee: „Ich muss aufs Klo“ 🚻

Ein Knopf in der App meldet dem **Fahrtleiter**, welcher Teilnehmer eine Toilettenpause braucht. Der Fahrtleiter kann auf der Karte einen passenden **Rastplatz** suchen und auswählen. Dieser wird als gemeinsamer Zwischenstopp übernommen; anschließend **aktualisiert TeslaTalk die Route für alle Teilnehmer**.

Die Meldung ist ein Pausenwunsch. Die Entscheidung über den Rastplatz bleibt beim Fahrtleiter. Mehrere Wünsche können später zu einem gemeinsamen Pausenstopp zusammengefasst werden.

## Technische Richtung

| Komponente | Aufgabe |
| --- | --- |
| React / TypeScript | Responsive Oberfläche für Tesla-Browser und Mobilgeräte |
| FastAPI | Anmeldung, Fahrten, Freunde, Chat, Fahrzeugdaten und API |
| SQLite | Persistente Speicherung auf einem Docker-Volume |
| WebSocket | Chat, Präsenz und Standortaktualisierungen innerhalb einer Fahrt |
| LiveKit | Selbst gehosteter Sprachfunk mit gleichzeitigen Sprechern |
| Tesla Fleet API | Offizielle Konto- und Fahrzeuganbindung |
| OIDC | Separater Administratorzugang |

## Ausprobieren

Voraussetzungen: Git, Python 3, OpenSSL und Docker Compose v2.

```bash
git clone https://github.com/Baodor/TeslaTalk.git
cd TeslaTalk
python3 scripts/configure.py --demo
docker compose up -d --build
```

Öffne **http://localhost:8780**. Der ausdrücklich aktivierte Demo-Modus erzeugt Beispieldaten und benötigt kein Tesla-Konto. Für eine echte Installation bleibt `DEMO_MODE=false`.

Für HTTPS auf einer neuen Installation:

```bash
python3 scripts/configure.py \
  --url https://talk.example.com \
  --voice-url wss://voice.example.com \
  --email du@example.com
docker compose -f compose.yaml -f deploy/compose.https.yaml up -d --build
```

Das Bootstrap-Skript überschreibt keine bestehende `.env`. Bei einer vorhandenen Installation passt du die Adressen direkt an und behältst die bestehenden Schlüssel.

### Mit vorhandenem Traefik starten

Die vollständige [compose.traefik.yaml](compose.traefik.yaml) enthält TeslaTalk, den LiveKit-Sprachserver, den Datenspeicher und die Router für dein externes `proxy`-Netzwerk. Für `teslatalk.glockb.de` gibt es eine **[deutsche Schritt-für-Schritt-Startanleitung](docs/START.de.md)** mit Schlüsselerzeugung, DNS, Ports, Tesla-Anmeldung, OIDC und PWA-Benachrichtigungen. Nach der Einrichtung startest du mit:

```bash
docker compose -f compose.traefik.yaml up -d --build
```

Traefik spricht TeslaTalk intern auf **8780** und LiveKit auf **7880** an. Für Audiodaten müssen zusätzlich **7881/TCP** und **7882/UDP** erreichbar sein. Die bisherigen Overlays unter `deploy/` bleiben für Kombinationen mit `compose.yaml` verfügbar.

[Einrichtung, Tesla Fleet API, OIDC und Backup](docs/SETUP.md) · [API-Dokumentation](docs/API.md)

## Auf den Home-Bildschirm

**iPhone/iPad:** In Safari öffnen → Teilen → **Zum Home-Bildschirm**. Anschließend über das neue Symbol starten und **Benachrichtigungen** aktivieren. Web-Push setzt hier iOS/iPadOS 16.4 oder neuer voraus. [Apple/WebKit erklärt die Unterstützung](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/).

**Android/Chrome:** Installationsknopf oder Browser-Menü nutzen und Benachrichtigungen ausdrücklich erlauben. Dein Icon kombiniert ein **Tesla-T mit einem Walkie-Talkie**. Installation und Push benötigen HTTPS; der lokale Demo-Aufruf über `localhost` ist die Entwicklungs-Ausnahme.

Benachrichtigungen verraten keine Chattexte, Kennzeichen oder Standorte. Mitfahrer erhalten Push nur während ihres gültigen Zugangs. Die Offline-Seite hält dich über Verbindungsprobleme informiert; Sprachfunk und aktuelle Daten benötigen Internet. Durchgehend laufender Sprachfunk im Hintergrund hängt vom Gerät und Browser ab.

## Was schon geprüft ist

- **29 Backend-Tests:** Rechte innerhalb einer Fahrt, PINs, Zeitgrenzen, private Freigaben, OAuth-Zustand, API-Schlüssel, Ranglisten und Push-Abonnements.
- **3 Browser-Tests:** Echtzeit-Chat mit zwei Fahrern, Mitfahrerzugang und Fahrtende, mobile Darstellung, Service Worker, Offline-Cache und Push-Einwilligung.
- **TypeScript und Produktionsbuild** erfolgreich. Ein optionaler LiveKit-Test und Docker-Build sind in GitHub Actions hinterlegt.

Push-Versand wird im Backend mit simulierten Push-Diensten geprüft; der Browser-Test prüft die Einwilligung mit einem simulierten Abonnement. Eine echte Tesla-Anmeldung und echte Push-Zustellung auf iOS/Android wurden hier noch nicht bestätigt.

## Bekannte Grenzen

- Standort- und Fahrzeugabfragen laufen standardmäßig alle **120 Sekunden** bei verbundenen Fahrern einer aktiven Fahrt. Das ist noch kein Fleet-Telemetry-Streaming und kann Tesla-API-Kosten verursachen.
- Verbrauchswerte erscheinen nur mit gemessenen Energie- und Kilometerzählern aus einer passenden Integration. V1 leitet keinen Verbrauch aus dem Akkustand ab.
- Ladeplanung, synchronisierte Routen, Musiksteuerung und Immich sind **Roadmap-Funktionen**. Der QR-Zugang ist bereits nutzbar; Foto-Uploads sind noch nicht angebunden.
- Ob Mikrofon und Browser während der Fahrt verfügbar sind, muss für Fahrzeug, Region und Firmware geprüft werden. V1 sendet keine Fahrzeugbefehle.
- Die Administration bietet zunächst eine Statusübersicht. Serverkonfiguration erfolgt über Umgebungsvariablen.
- Ein Server nutzt einen FastAPI-Prozess mit SQLite. Mehrere Instanzen und verteilte Skalierung folgen später.

## Lizenz

TeslaTalk steht unter der [GNU Affero General Public License v3.0](LICENSE). Bei veränderten Versionen, die als Netzwerkdienst angeboten werden, ist Nutzern der entsprechende Quellcode bereitzustellen.

TeslaTalk ist nicht mit Tesla, Inc. verbunden und wird nicht von Tesla unterstützt. Tesla und die Fahrzeugnamen sind Marken ihrer jeweiligen Inhaber.
