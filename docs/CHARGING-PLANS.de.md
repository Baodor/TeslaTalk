# Gemeinsame Ladepläne und ABRP

Stand: 13. Oktober 2026. Excel-/CSV-/GPX-Import, Vorschau, JSON-Rückexport und Übertragung des nächsten gemeinsamen Halts sind implementiert. Eine komplette native Tesla-Zwischenzielliste und das automatische Auslesen sämtlicher Tesla-Ladehalte sind weiterhin offen.

## Datei hochladen

Unter **Fahrt → Karte → Gemeinsamer Ladeplan** lädt der Fahrtleiter eine Datei hoch. Unterstützt sind:

| Format | Inhalt |
| --- | --- |
| ABRP Excel (.xlsx) / CSV | Routentabelle mit Wegpunkt/Name und expliziten Latitude/Longitude-Spalten oder Google-Maps-Stationslinks mit Zielkoordinaten; genau eine Excel-Tabelle |
| GPX | Genau eine Route mit benannten `rtept`-Stopps oder eine geordnete Liste benannter `wpt`-Wegpunkte; Koordinaten verpflichtend |
| TeslaTalk JSON | Der eigene verlustfreie Export mit `title` und `stops`; kein beliebiges proprietäres ABRP-JSON |

Maximal 500 KB und 50 Stopps. Reine `trkpt`-Tracks werden abgewiesen: Straßenpunkte sind keine sicheren Ladehalte. XML-Entitäten werden nicht aufgelöst; URLs werden beim Import nicht geöffnet. Falls dein ABRP-Export nur einen Track oder keine benannten Ladehalte enthält, ist er für diesen Import ungeeignet. ABRP bietet **Nach Excel exportieren** an (siehe [offizielle Oberflächentexte](https://github.com/Iternio-Planning-AB/abrp-translations/blob/master/de.json)). Diesen Export in TeslaTalk hochladen. Fehlen eindeutige Koordinaten/Stationslinks, Breitengrad/Längengrad in der Tabelle ergänzen; Namen werden nicht automatisch geocodiert. Unser Parser unterstützt das Standard-XLSX-Format samt Zell-Hyperlinks und zwischengespeicherten Werten; ein echter Export deiner aktuellen ABRP-Version muss noch getestet werden. GPX ist ein zusätzliches Austauschformat; eine native ABRP-GPX-Exportfunktion wird hier nicht vorausgesetzt.

Die Vorschau zeigt Reihenfolge, Namen, Koordinaten, Stationstyp und vorhandene Adresse/Google-Places-ID. Bekannte Stationsnamen dienen nur als Vorschlag für den Typ: vor dem Speichern prüfen und nötigenfalls korrigieren. Eine echte Places-ID kann ergänzt werden; keine ID erfinden. **Geprüften Ladeplan speichern** speichert nur Daten und sendet keinen Fahrzeugbefehl. **Ladeplan exportieren** erstellt einen TeslaTalk-JSON-Export, der dieselben Stationen und Referenzen wieder einlesen kann.

Excel-/CSV-Spalten `Wegpunkt`/`Waypoint`/`Name`, `Breitengrad`/`Latitude`, `Längengrad`/`Longitude`, `Ladedauer`/`Charge duration`, `Adresse`/`Address` und vorhandene Stationslinks werden gelesen. Formeln werden nicht ausgeführt und externe Links nicht geöffnet. Größenlimits gelten auch für die entpackten Excel-Daten.

GPX-Erweiterungen `google_place_id`/`googleplaceid`, `operator` und `address` werden übernommen. Das eigene JSON enthält beispielsweise:

```json
{
  "format": "teslatalk-route",
  "version": 1,
  "title": "Gemeinsame Fahrt",
  "stops": [
    {"name": "Konkrete Ladestation", "latitude": 50.1, "longitude": 8.7,
     "kind": "charging", "operator": "", "address": "", "google_place_id": null},
    {"name": "Ziel", "latitude": 53.55, "longitude": 10,
     "kind": "destination", "operator": "", "address": "", "google_place_id": null}
  ]
}
```

Dies sind Formatbeispiele, keine geprüften Ladestationskoordinaten.

## An die Autos senden

1. Jeder Fahrer erlaubt **Automatische Zielübernahme in meinem Auto** für sein aktuelles Auto und diese Fahrt. Mitfahrer und reine Zuschauer haben keine Fahrzeugrechte.
2. Der Fahrtleiter wählt **Diesen Halt an die freigegebenen Autos senden** beim nächsten gemeinsamen Stopp. Sein eigenes Auto wird durch diese ausdrückliche Aktion ebenfalls angemeldet. Alle zustimmenden Autos erhalten denselben Halt als Navigationstext mit Stationsnamen, Adresse und Google-Maps-Link; eine vorhandene Places-ID bleibt erhalten. Supercharger und andere Betreiber können in der Liste stehen.
3. Jeder Tesla berechnet den Abschnitt selbst. Die App liest die Navigation nach erfolgreichem Senden sowie im sparsamen Routenintervall aus dem Planungsauto; ein sofortiges Auslesen kann noch vor der Neuberechnung liegen. **Route aus Auto abrufen** bleibt verfügbar. Eine vollständige Straßenlinie braucht weiterhin Fleet Telemetry `RouteLine`.
4. Jeder Fahrer prüft am Auto **Tesla zeigt diesen Halt als Ladestation** und danach gegebenenfalls **Vorkonditionierung wird im Auto angezeigt**. Der Fahrtleiter sieht diese Rückmeldungen. Bestätigungen gelten nur für Planversion, aktuellen Halt und eigenes aktuelles Fahrzeug; Plan-/Autowechsel macht alte Bestätigungen ungültig.
5. Beim nächsten Abschnitt sendet der Fahrtleiter den nächsten Halt. Speichern/Löschen eines Plans oder eine Pausenmeldung brechen eine schon laufende Fahrzeugnavigation nicht automatisch ab.

Befehlsergebnisse werden mit Auftrags-ID gespeichert. Ein wiederholter identischer Auftrag sendet nicht erneut. Bei Verbindungsabbruch den **Auftragsstatus abrufen** und tatsächlich am Auto prüfen; es gibt keine automatischen Befehlswiederholungen. Ein erneuter Versuch braucht die bewusste erneute Freigabe durch den jeweiligen Besitzer. Fahrtende und Widerruf stoppen weitere Befehle. Navigationsbefehle brauchen `TESLA_NAVIGATION_COMMANDS=true`, `vehicle_cmds` und die passende Fahrzeug-/Proxy-Anbindung, siehe [Fahrzeugsteuerung](VEHICLE-CONTROLS.de.md).

## Ladestation und Vorkonditionierung

Eine Koordinate oder erfolgreiche HTTP-Antwort beweist keine Zuordnung zum Tesla-Ladestationsverzeichnis. Auch eine Google-Places-Referenz wird erhalten, aber ihre Erkennung durch Tesla ist damit noch nicht verifiziert. Insbesondere bei Fremdladern hängen Zuordnung und Vorkonditionierung vom Fahrzeug und seiner Software ab. Die Checkboxen sind manuelle Rückmeldungen, kein Heizbefehl und keine automatische Fahrzeugprüfung.

ABRP beschreibt seine eigene Funktion [Send to Tesla](https://abetterrouteplanner.com/resources/article/2023-09-08_abrp-4-6-0) mit echten Ladestationsdetails für Vorkonditionierung. Das bestätigt nicht, dass ein beliebiger GPX-Koordinatenexport dieselben Details enthält. Falls Tesla den importierten Halt nicht als Ladeziel erkennt, die konkrete Station im Fahrzeugnavi auswählen und die Anzeige prüfen.

Die [Tesla-API](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands) dokumentiert eigene GPS-, Supercharger- und Waypoint-Befehle. Im aktuell geprüften offiziellen [Command-Proxy](https://github.com/teslamotors/vehicle-command/blob/main/pkg/proxy/command.go) ist unter den Navigationsbefehlen nur `navigation_request` implementiert, als REST-Weiterleitung. TeslaTalk sendet deshalb den nächsten Halt einzeln, keine ungetestete vollständige Zwischenzielliste. Die [Telemetriefelder](https://developer.tesla.com/docs/fleet-api/fleet-telemetry/available-data) liefern Ziel/Kennzahlen und RouteLine, keine vollständige geordnete Ladehaltefolge.

## ABRP-Zugänge und weitere Planung

ABRP-Teilen-Links mit Plan-UUID können nach Kontoverbindung als ursprüngliche **Planungsparameter** übernommen werden. Der Reiter **Ladeplanung** berechnet anschließend eine neue Route über die Iternio-v2-Planning-API. Dies ist ausdrücklich keine identische Übernahme einer bereits gespeicherten berechneten Route. Die Fahrzeugvariante und mehrere Ladenetze können gewählt werden; EXCLUSIVE beschränkt auf die gewählten Netze. Eine vorhandene Iternio-Ladestations-ID wird zur Google-Places-ID aufgelöst, soweit der Anbieter eine Zuordnung liefert. [Einrichtung, Kosten und Tests](ABRP.de.md).

In ABRP können [Netze bevorzugt/vermieden](https://abrp.featurebase.app/help/articles/4671857-avoid-and-prefer) und [Ladekarten](https://abrp.featurebase.app/help/articles/5884894-charge-cards) berücksichtigt werden. Die dort exportierten konkreten Stationen können nach Prüfung über die Datei übernommen werden. TeslaTalk berechnet derzeit keine Ladezeiten/Reserven für die ganze Gruppe und garantiert keine freien Ladeplätze oder identischen Ladebeginn. Live-Belegungsanzeigen bleiben Roadmap.

Alle Tesla-Befehle gehen ausgehend über HTTPS. Für den vorhandenen CGNAT-/WireGuard-Aufbau sind keine zusätzlichen öffentlichen Ports nötig. Der Command-Proxy bleibt intern. [Testcheckliste](TEST-CHECKLIST.de.md).
