# ABRP-/Iternio-Ladeplanung und Tesla-Anmeldung

Stand: 13. Oktober 2026. Die Implementierung wurde gegen die [veröffentlichte OpenAPI-Spezifikation 2.0.3](https://api.iternio.com/swagger-ui/spec/prod/IternioPlanning.out.yaml) geprüft. Alle automatischen Tests verwenden isolierte Antworten; hier wurden weder reale Kontozugangsdaten noch kostenpflichtige Pläne angefordert.

## Installation

In der bestehenden lokalen `.env` ergänzen:

```dotenv
ABRP_PLANNING_API_KEY=<DEIN_ITERNIO_PLANNING_API_KEY>
ABRP_DAILY_PLAN_LIMIT=20
```

Ein kostenloser Telemetrie-Schlüssel genügt nicht. Laut Iternio sind Einrichtung und erfolgreiche `/plan`-Berechnungen kostenpflichtig; Preise/Zugangsrechte mit dem Anbieter klären. Metadatenaufrufe sind laut Spezifikation kostenfrei. Die [API-Seite](https://abetterrouteplanner.com/resources/api) beschreibt die getrennten Zugänge. Der Key bleibt serverseitig im `X-API-KEY`-Header, nie in einem Browserlink oder im API-/LLM-Export.

Danach mit denselben Compose-Dateien neu erstellen:

```bash
docker compose -f compose.traefik.yaml -f compose.vehicle-controls.yaml up -d --build
```

Ohne Key zeigt der neue Reiter eine Einrichtungsinformation und führt keine Berechnung aus. Keine neuen öffentlichen Ports nötig; Iternio-Verbindungen sind ausgehendes HTTPS. Tageslimit zählt alle begonnenen Berechnungsaufträge dieser Instanz ab Mitternacht in `APP_TIMEZONE`, auch unbestätigte/fehlgeschlagene, damit es nicht durch Fehler/Wiederholungen umgangen wird. Ein Zurückladen derselben Auftrags-ID zählt nicht neu.

## Konto und Link

Der Fahrtleiter öffnet **Ladeplanung → ABRP-Konto und Fahrzeugkatalog**. Benutzername/E-Mail und Passwort werden über die dokumentierte Iternio-v2-Schnittstelle `POST /auth/login` übertragen. Dieser Endpunkt ist beim Anbieter als **alpha** markiert und braucht einen dafür freigegebenen API-Key. TeslaTalk speichert nur die erhaltene Sitzung mit ihrer Ablaufzeit verschlüsselt; Passwort und Refresh-Token werden nicht gespeichert. Es gibt keinen undokumentierten Refresh-Aufruf. Bei Ablauf erneut verbinden. **ABRP-Verbindung entfernen** löscht die lokale Sitzung und den Modellcache.

Dies ist eine API-Kontoverbindung, keine OAuth-Weiterleitung. Ob dein Kontotyp mit dieser Anmeldung funktioniert (etwa externe Apple-/Google-Anmeldung oder zusätzliche Verifizierung), muss beim Anbieter geprüft werden. OAuth `get_plan` beschreibt der Anbieter separat, dessen verkürzter Antwortvertrag ist nicht automatisch mit der v2-Sitzung gleichgesetzt.

Im Feld **ABRP-Teilen-Link** einen vollständigen ABRP-Link mit `plan_uuid=<UUID>` einsetzen. Zugelassen sind die bekannten ABRP-Domains; Kurzlinks oder fremde URLs werden nicht geöffnet. Die App liest mit der eigenen ABRP-Sitzung `GET /abrp/plan/{planId}/request`. Der Vertrag liefert **ursprüngliche Parameter**, nicht die gespeicherte berechnete Route. Start/Ziel/Zwischenhalte, Fahrzeug-Typecode, Akku/Reserve und bevorzugte/exklusive Ladenetze werden in das Formular übernommen. Andere gespeicherte Einstellungen (etwa Wetter, Verbrauchskalibrierung oder Straßenvermeidung) werden dabei nicht als übernommen behauptet. Der Hinweis in der Oberfläche nennt diese Grenze.

## Berechnung und Verteilung

1. Ganz oben bleiben Empfehlungen für geringste gemeldete Reichweite und niedrigsten Akku. Ein **Gruppenfahrzeug** wählen und den aktuellen Abfahrtsakku prüfen; Browser-GPS liefert keine Batterieprognose. Ein unpassender/staler Akkustand kann manuell korrigiert werden.
2. Im Iternio-Fahrzeugkatalog die **exakte Modell-, Batterie- und Antriebsvariante** auswählen. Ein generischer Tesla-Modellname reicht dafür nicht. Der Katalog braucht laut API eine ABRP-Sitzung; es werden keine Typecodes geraten.
3. Start/Ziel und optionale Zwischenstopps eintragen. Der aktuelle Browserstandort des gewählten Autos kann als Start übernommen werden. Aufenthaltszeiten werden als Sekunden an Iternio übergeben.
4. Mehrere Ladenetze auswählen. Ohne Auswahl sind alle passenden Netze zulässig. Auswahl bevorzugt diese Netze; **Ausschließlich** übergibt `EXCLUSIVE` und lässt nur diese Netze zu. Wenn so keine Route fahrbar ist, wird das gemeldet; Netze werden nicht stillschweigend ausgetauscht.
5. Datenübermittlung und mögliche Planungskosten bewusst bestätigen. Erst **Laderoute berechnen** sendet einen `/plan`-Aufruf. Kein automatisches ABRP-Polling oder kostenpflichtiges Nachplanen.
6. TeslaTalk zeigt den berechneten Straßenverlauf (Polyline5/6 nach expliziter API-Präzision), geordnete Lade-/Zwischenstopps, Strecke und Dauer. Prognosen zu Ankunfts-/Abfahrtsakku und Ladezeit gelten für das gewählte Planungsfahrzeug, nicht automatisch für jedes Auto.
7. Ladehalte prüfen und **Geprüften Ladeplan speichern**. Speichern sendet keine Fahrzeugbefehle. Der Plan ist danach für die Gruppe sichtbar und verlustfrei als JSON exportierbar.
8. **Diesen Halt an die freigegebenen Autos senden** verteilt den nächsten gemeinsamen Halt über die bestehende Tesla-Anbindung. Jeder Besitzer gibt Zielübernahme für sein aktuelles Auto frei. Andere Fahrer und Mitfahrer/Zuschauer können keine Gruppenbefehle senden.

Iternio-Ladestations-IDs werden mit `/charger/_google-place-ids` auf echte, vom Anbieter gelieferte Google-Places-IDs abgebildet. Netzname/Netz-ID werden aus der Station ergänzt. Fehler bei optionalen Metadaten verwerfen die bereits berechnete Route nicht. Fehlende Referenzen bleiben unbestätigt, werden nicht erfunden und bleiben in der Stationsübersicht erkennbar.

Der aktuell verwendete Tesla-Proxy überträgt weiterhin **einen Halt nach dem anderen**, keine vollständige native Waypoint-Liste. Eine erfolgreiche HTTP-Übertragung oder eine Iternio-/Google-Stationsreferenz beweist noch keine Tesla-Verzeichniszuordnung oder Vorkonditionierung. Beide Anzeigen im eigenen Auto prüfen und erst dann die Rückmeldung setzen. [Stationsprüfung](CHARGING-PLANS.de.md).

## Unterbrechungen

Die Auftrags-ID und ein unbestätigter Zustand werden **vor** dem ausgehenden Planaufruf gespeichert. Dieselbe ID wird nie erneut berechnet. Bei Verbindungsabbruch **Berechnungsstatus abrufen** verwenden; dieser Abruf liest nur die Datenbank. Ergebnisse bleiben beim Reiterwechsel erhalten. Nach unbestätigtem Ausgang kann **Neue Berechnung bewusst starten** gewählt werden; die Kostenbestätigung wird dafür zurückgesetzt. Eine neue ID kann erneut Kosten verursachen.

## Tesla-Login

Anmeldung über eine abweichende LAN-IP/Hostname wird zuerst auf die konfigurierte `APP_URL` verschoben, damit Login-Cookie und Callback denselben Host verwenden. Parallele Versuche haben eigene Cookie-Bindungen und PKCE-Verifier. Falsche/fehlende Cookie-Bindung wird weiterhin abgelehnt; die App zeigt eine UTF-8-Seite mit Neustart-/Startseitenlink. Bei einem bereits verbrauchten/alten Rücksprung und weiterhin gültiger TeslaTalk-Sitzung geht es ohne erneuten Codeaustausch zur Startseite.

Dass Tesla bei einem neuen autorisierten Versuch kein Passwort erneut verlangt, kann an einer bestehenden Tesla-SSO-Sitzung liegen. Auf dem iPhone die Anmeldung im selben Browserfenster abschließen. Ein Wechsel zwischen Safari und einer installierten Web-App mit getrennten Cookies wird nicht durch das Abschalten der Sicherheitsprüfung umgangen.
