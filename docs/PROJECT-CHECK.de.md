# Projektprüfung vom 5. Oktober 2026

Die Prüfung umfasst das aktuelle Backend, Frontend, Authentifizierung und Zugriffsrechte, Push-Abonnements und Versand, Fahrten und Mitfahrer, Standortdaten, Fahrzeugabruf, Sprachfunk, PWA/Offline-Verhalten, Konfigurationsskripte, Docker/Traefik und die vorhandenen Integrationstests. Eine Prüfung des Codes ersetzt keinen Test der tatsächlichen iPhone-Zustellung oder des konkreten VPS-Netzwerks.

## Behobene Befunde

| Bereich | Problem | Korrektur und Prüfung |
| --- | --- | --- |
| Persönlicher Push-Test | Zwei aufeinanderfolgende Serveranfragen: Geräteabgleich, danach Versand. Eine im Hintergrund angehaltene Seite konnte vor der zweiten Anfrage stehen bleiben. Eine erneuerte Anmeldung erforderte außerdem den getrennten Abgleich. | Aktuelles Abonnement und Testwunsch werden zusammen übermittelt. Der Server validiert Gerätebesitz und Sitzung vor dem Versand. Backendtest für eine erneuerte Sitzung und Browsertest ohne zusätzliche Subscribe-Anfrage. |
| Wiederholte Push-Tests | Wiederholte Tests verwendeten denselben Tag und konnten bestehende Mitteilungen ersetzen. | Jeder persönliche und administrative Test erhält einen eigenen Tag. Reguläre Chat-Nachrichten behalten ihre Gruppierung und fordern einen erneuten Alarm an. |
| Push-Hintergrundprozess | Ein Fehler außerhalb der einzelnen Zustellung, beispielsweise eine zeitweise blockierte Datenbank, beendete den Versandprozess dauerhaft. | Der Prozess protokolliert nur die Fehlerklasse und versucht im nächsten Durchlauf erneut zu arbeiten. Wiederanlauf nach injiziertem Datenbankfehler geprüft. |
| Wartung und Fahrzeugabruf | Ein unerwarteter Fehler konnte Sitzungsbereinigung, Raumabschaltung und Fahrzeugabfragen dauerhaft beenden. | Wiederanlauf im nächsten Durchlauf; Test belegt die anschließende Entfernung einer abgelaufenen Sitzung. |
| Tesla-Fahrzeugdaten | `vehicle_config: null` löste einen Fehler aus. Ein fehlendes Modell wurde als Model 3 dargestellt; `modely` wurde zu „Model MODELY“. Ungültige Datentypen verursachten ungefangene Ausnahmen. | Fehlende Konfiguration ist zulässig, unbekannte Modelle erscheinen als „Tesla“, bereits bekannte Modelle bleiben erhalten. Modellcodes werden korrekt formatiert; fehlerhafte Daten ergeben eine kontrollierte HTTP-502-Antwort. Regressionstests für diese Fälle. |
| Anmeldung in der Oberfläche | Ein Fehler beim Laden von Fahrzeugen oder Einladungen setzte ein bereits erfolgreich angemeldetes Konto wieder auf den Login-Bildschirm. | Teilanfragen werden getrennt ausgewertet; verfügbare Daten und Anmeldung bleiben bestehen. Der Fehler wird angezeigt. Browsertest mit nicht verfügbaren Fahrzeugdaten. |
| Sprachaktivierung | Trennen und Effektbereinigung konnten denselben AudioContext zweimal schließen und eine unbehandelte Promise-Ablehnung auslösen. | Referenzen werden vor asynchronem Trennen gelöst; bereits geschlossene Kontexte werden nicht erneut geschlossen. Der reale Zwei-Sprecher-Test umfasst nun Sprachaktivierung und anschließendes Trennen. |
| Konfigurationsskript | URLs mit leerem Benutzernamen und gesetztem Passwort wurden nicht vollständig als URLs mit Zugangsdaten erkannt. | Passwortfelder werden ebenfalls abgewiesen, bevor Dateien oder Schlüssel angelegt werden. |

## Immich: tatsächlich vorhandener Stand

Immich ist im aktuellen Projekt eine Roadmap-Funktion. Das Backend liefert einen berechneten Albumnamen mit `status: planned` und `url: null`. Es gibt keine Immich-Clientimplementierung, keine dafür vorgesehenen Konfigurationseinstellungen oder Zugangsdaten, keine Album-ID-Speicherung und keine Upload-Endpunkte. Deshalb lassen sich echte Albumanlage, Foto-Uploads und Immich-Berechtigungen derzeit nicht testen.

Bereits implementiert und getestet sind benannte Mitfahrer mit persönlichem PIN, zeitlich begrenzter Mitfahrer-Zugang und ein separat widerrufbarer öffentlicher Leselink zur Fahrtübersicht. Dieser Link enthält keine privaten Nachrichten, Kennzeichen oder GPS-Verläufe. Er ist noch kein Immich-Albumbetrachter.

Eine vollständige Immich-Anbindung braucht einen eigenen Implementierungsschritt: Verbindung zur Instanz des Fahrtleiters, geschützte Zugangsdaten, Albumanlage und Zuordnung, Uploads mit serverseitiger Kontrolle des Fahrtzeitraums und eine getrennte Lesefreigabe. Die aktuellen offiziellen Schnittstellen stehen unter [api.immich.app](https://api.immich.app/); die [Immich-Freigabedokumentation](https://docs.immich.app/features/sharing/) beschreibt Album- und Leseberechtigungen. README und Oberfläche weisen den fehlenden Anschluss ausdrücklich aus.

## Verifikation und Praxistest

- 128 Backendtests, einschließlich Zugriffsrechten, OIDC, Gastablauf, API-Schlüsseln, Telemetrie, Push-Zustellung und den neuen Fehlerfällen.
- TypeScript-Prüfung und Produktionsbuild des Frontends.
- 12 Browsertests in der CI, einschließlich persönlichem und administrativem Push-Ablauf, Service Worker, privaten Offline-Daten, Gastablauf und zwei gleichzeitig veröffentlichten Mikrofonen mit realem LiveKit.
- CI prüft die Traefik-Konfiguration mit und ohne Zertifikat-Resolver sowie Build und Start des Produktionscontainers unter seinem Anwendungsbenutzer mit persistentem Datenvolume.
- Installierte Python-Abhängigkeiten sind konsistent (`pip check`); Frontend-Abhängigkeiten entsprechen den installierten Paketversionen (`npm ls`).

Die Browser-Push-Tests prüfen den Anwendungscode und die übergebenen Benachrichtigungsoptionen. Sie senden keine echten Apple-Push-Mitteilungen und prüfen keinen iPhone-Benachrichtigungston. Nach dem Update muss die persönliche Testnachricht auf dem betroffenen iPhone nochmals mit ihrer angezeigten Annahmezeit verglichen werden. Der vom Betreiber gemeldete unmittelbar eintreffende Admin-Test bestätigt bereits einen funktionierenden Versandweg für dieses Gerät.

Die dokumentierte CGNAT-Konfiguration bleibt: öffentliche VPS-IP `85.215.167.177`, Weiterleitung von `7881/TCP` und `7882/UDP` über WireGuard an `10.66.0.2`, LiveKit mit der öffentlichen VPS-IP als angekündigter Adresse. Die Projektprüfung ändert diese installierten Netzwerkregeln nicht und belegt keine externe Audioverbindung über das konkrete Mobilfunknetz.
