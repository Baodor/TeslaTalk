# ABRP-/Iternio-Ladeplanung und Tesla-Anmeldung

Stand: 13. Oktober 2026. Die Implementierung wurde gegen die [veröffentlichte OpenAPI-Spezifikation 2.0.3](https://api.iternio.com/swagger-ui/spec/prod/IternioPlanning.out.yaml) geprüft. Alle automatischen Tests verwenden isolierte Antworten; hier wurden weder reale Kontozugangsdaten noch kostenpflichtige Pläne angefordert.

## Standard: ohne kostenpflichtigen Planning-Key

Der Reiter **Ladeplanung** startet mit **Mit deinem ABRP-Konto planen**. Diese Oberfläche verwendet weder die Iternio-API noch die Tesla-API. Sie zeigt ausschließlich die bereits in der Gruppe gespeicherten Fahrzeugwerte. Es ist keine Änderung an `.env` nötig.

1. Gruppenfahrzeug auswählen. Empfehlungen für geringste gemeldete Reichweite und niedrigsten Akku stehen oben. Ein älterer Akkuwert wird als solcher angezeigt; TeslaTalk löst keinen zusätzlichen Tesla-Abruf aus.
2. Start, Ziel und Zwischenstopps angeben. Ein höchstens fünf Minuten alter Browserstandort des ausgewählten Autos kann ausdrücklich als Start übernommen werden. Adresse oder `Breitengrad, Längengrad` verwenden.
3. Die Übermittlung der Routenpunkte bestätigen und **ABRP-Link und QR-Code vorbereiten** wählen. QR und Direktlink öffnen ABRP; bis zum Öffnen bleibt die Vorbereitung lokal. Der Link enthält nur `destinations`, keine Benutzer-/Fahrzeug-IDs, VINs, Tokens, Kennzeichen oder Ladekarten. Lange Links bleiben direkt nutzbar, auch wenn sie nicht in einen QR-Code passen. Eine Änderung entfernt die alte Übergabe.
4. In ABRP in deinem eigenen Konto anmelden und das passende gespeicherte Fahrzeug auswählen. Den angezeigten Akku aus TeslaTalk mit **Abfahrtsakku kopieren** übernehmen. Das ist ein Datenstand, **keine automatische Telemetrie-Synchronisierung**. Modell-/Batterievariante, tatsächlichen Abfahrtsakku, Ladekarten und Ladenetze dort vor der Berechnung prüfen.
5. In ABRP berechnen, nach Excel exportieren und unten in TeslaTalk als Routen-Datei hochladen. Stopps/Koordinaten/Stationsreferenzen prüfen, speichern und den nächsten gemeinsamen Halt an die freigegebenen Fahrzeuge senden. Die Stoppkarte zeigt auch importierte Pläne. Eine Straßenlinie wird nur angezeigt, wenn sie in den Daten vorhanden ist.

**Echte QR-Anmeldung:** ABRP auf dem zweiten Gerät öffnen und dort **Login mit ABRP-App** wählen. Auf dem bereits angemeldeten Handy in den ABRP-Kontoeinstellungen **Login remote app** öffnen und den von ABRP erzeugten Login-QR-Code scannen. [Offizielle Anleitung](https://abrp.featurebase.app/help/articles/2873458-log-in-via-qr-code). Der in TeslaTalk angezeigte QR-Code öffnet dagegen die Route und ist ausdrücklich kein Login-Token. Die ABRP-Anmeldung bleibt in ABRP; TeslaTalk besitzt dadurch keine Kontositzung.

Die [offiziell beschriebenen Deep Links](https://abetterrouteplanner.com/resources/api) erlauben eine Übergabe an die ABRP-App. Zusätzlich wurde am 13.10.2026 die öffentlich ausgelieferte Web-App geprüft: `destinations` wird als JSON gelesen; `car_model` hat einen separaten Handler, der vor der Routenübernahme zurückkehrt. Ein kompatibler SoC-URL-Handler wurde dort nicht gefunden. Deshalb kombiniert TeslaTalk diese Parameter nicht und behauptet keinen automatisch übernommenen Akku. Quelle: öffentlich verlinkter [ABRP-App-Build](https://web.abetterrouteplanner.com/_expo/static/js/web/App-d553813b302629be0b99fa815b82c509.js), nur lesend untersucht; keine Anwendungs-API-Keys oder fremden OAuth-Clients übernommen. Die tatsächliche Übernahme muss mit deiner ABRP-Version geprüft werden.

Ein ABRP-Teilen-Link liefert ohne freigegebenen API-Zugang weiterhin keine fertige berechnete Route an den TeslaTalk-Server. Ein vollautomatischer Rückkanal ist mit diesem kostenlosen Ablauf nicht implementiert. Der offizielle Partner-OAuth-Zugang benötigt eine bei Iternio registrierte Anwendung; der Antwortvertrag für `get_plan` wird laut Anbieter separat abgestimmt. Der kostenlose [Telemetry-Zugang](https://abetterrouteplanner.com/resources/api) kann Fahrzeugdaten übertragen, ersetzt jedoch keinen Planabruf und ist hier nicht als bestehende Verbindung dargestellt.

## Optionale kostenpflichtige API

Die bisherige Iternio-Integration ist unter **Optionale kostenpflichtige API anzeigen** erreichbar. Erst das Öffnen dieser erweiterten Oberfläche lädt deren Kontostatus/Katalog; ein Plan wird weiterhin nur nach ausdrücklicher Kostenbestätigung angefordert. Sie ist keine Voraussetzung für den Standardablauf.

### Installation

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

Ohne Key ist die kostenlose Übergabe verfügbar. Die optionale API-Oberfläche zeigt eine Einrichtungsinformation und führt keine API-Berechnung aus. Keine neuen öffentlichen Ports nötig; Iternio-Verbindungen sind ausgehendes HTTPS. Tageslimit zählt alle begonnenen Berechnungsaufträge dieser Instanz ab Mitternacht in `APP_TIMEZONE`, auch unbestätigte/fehlgeschlagene, damit es nicht durch Fehler/Wiederholungen umgangen wird. Ein Zurückladen derselben Auftrags-ID zählt nicht neu.

## Konto und Link

Der Fahrtleiter öffnet **Ladeplanung → Optionale kostenpflichtige API anzeigen → ABRP-Konto und Fahrzeugkatalog**. Benutzername/E-Mail und Passwort werden über die dokumentierte Iternio-v2-Schnittstelle `POST /auth/login` übertragen. Dieser Endpunkt ist beim Anbieter als **alpha** markiert und braucht einen dafür freigegebenen API-Key. TeslaTalk speichert nur die erhaltene Sitzung mit ihrer Ablaufzeit verschlüsselt; Passwort und Refresh-Token werden nicht gespeichert. Es gibt keinen undokumentierten Refresh-Aufruf. Bei Ablauf erneut verbinden. **ABRP-Verbindung entfernen** löscht die lokale Sitzung und den Modellcache.

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
