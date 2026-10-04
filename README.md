<div align="center">

# TeslaTalk

### Gemeinsam unterwegs. Verbunden bleiben.

**Sprachfunk · Fahrten · Live-Karte · Freunde · Roadtrips**

![License](https://img.shields.io/badge/Lizenz-AGPLv3-8eefbb?style=flat-square&labelColor=101a20)
![Self hosted](https://img.shields.io/badge/Self--Hosted-Docker-8eefbb?style=flat-square&labelColor=101a20)
![Status](https://img.shields.io/badge/Status-V1_im_Aufbau-f5c76d?style=flat-square&labelColor=101a20)

Deine Gruppe. Deine Fahrt. Dein Server.

</div>

---

TeslaTalk verbindet Freunde, die gemeinsam mit ihren Teslas unterwegs sind. Eine Fahrt bündelt Sprachfunk, Chat und eine Karte der Teilnehmer. Die Oberfläche ist für den Tesla-Browser gedacht und funktioniert auch auf Handy, Tablet und Computer. Der Server läuft selbst gehostet in Docker.

> Die erste Implementierung wird gerade aufgebaut. Diese Übersicht trennt den festgelegten Umfang von späteren Erweiterungen. Fahrzeugfunktionen werden über die offiziellen Tesla-Schnittstellen angebunden; TeslaTalk ist ein unabhängiges Projekt.

## Erste Version

| Bereich | Umfang für V1 |
| --- | --- |
| Tesla-Anmeldung | Offizielle OAuth-Weiterleitung; TeslaTalk nimmt keine Tesla-Passwörter entgegen |
| Fahrzeuge | Fahrzeuge des Kontos abrufen, Fahrzeug auswählen und Favoriten festlegen |
| Freunde | Anfragen, Annahme und Einladungen über Benutzername, Kennzeichen oder vorhandene E-Mail-Adresse |
| Fahrten | Name, Ziel, Beginn und Ende; Beitritt per PIN oder Einladung |
| Karte | Standort und Fahrzeugdaten ausschließlich innerhalb der eigenen Fahrt |
| Sprachfunk | Mehrere Sprecher gleichzeitig; Push-to-Talk und Sprachaktivierung; selbst gehosteter LiveKit-Server |
| Chat | Persistenter Fahrt-Chat, später auch aus der mobilen App nutzbar |
| Mitfahrer | Persönlicher Name und PIN, QR-Beitritt ohne Tesla-Konto, auf den Fahrtzeitraum begrenzt |
| Historie | Vollständige Speicherung der erfassten Daten und Export; Rankings für Verbrauch, Zeit und Durchschnittstempo |
| Administration | Separater Administratorzugang über OIDC |
| API | Grundlage für spätere Apps und persönliche API-Schlüssel |

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

### iOS- und Android-App

- Eigene Serveradresse hinterlegen.
- Fahrten, Fahrzeugdaten, Karte, Sprachfunk und Chat unterwegs nutzen.
- Mitfahrerzugang über QR-Code unterstützen.

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

Einrichtungsanleitung, Screenshots, API-Dokumentation und überprüfte Grenzen folgen mit der lauffähigen ersten Version.

## Lizenz

TeslaTalk steht unter der [GNU Affero General Public License v3.0](LICENSE). Bei veränderten Versionen, die als Netzwerkdienst angeboten werden, ist Nutzern der entsprechende Quellcode bereitzustellen.

TeslaTalk ist nicht mit Tesla, Inc. verbunden und wird nicht von Tesla unterstützt. Tesla und die Fahrzeugnamen sind Marken ihrer jeweiligen Inhaber.
