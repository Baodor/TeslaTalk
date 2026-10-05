# Gemeinsame Ladestopps und ABRP

Stand: 5. Oktober 2026. Dies ist ein Integrationsentwurf; TeslaTalk implementiert derzeit Fahrzeugauswahl, Navigationsabruf und zustimmungsgebundene Zielbefehle. ABRP-Anbindung und Übertragung einer vollständigen Ladehaltefolge sind noch nicht implementiert.

## Tesla-App: Lesen und Senden sind zwei getrennte Funktionen

Tesla dokumentiert [`navigation_waypoints_request`](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands) zum Senden einer Zwischenzielliste und `navigation_gps_request` mit Reihenfolgeoption. Das bedeutet noch nicht, dass TeslaTalk die geplanten Ladehalte lesen kann: Die [öffentlichen Fahrzeug-/Telemetriefelder](https://developer.tesla.com/docs/fleet-api/fleet-telemetry/available-data) dokumentieren Navigationsziel und Kennzahlen sowie die Routenlinie, keine vollständige geordnete Ladestoppliste. Aus der Linie können weder sichere Stationszuordnung noch nötige Ladeziele abgeleitet werden. Dass die Tesla-App diese Angaben anzeigt, belegt keine freigegebene Leseschnittstelle für Drittanbieter.

Vor einer Umsetzung der Zwischenstopp-Befehle müssen Payload, Fahrzeugunterstützung und gegebenenfalls signierte Vehicle-Command-Verbindung geprüft werden. Beim geprüften offiziellen [Command-Proxy](https://github.com/teslamotors/vehicle-command/blob/main/pkg/proxy/command.go) fehlt am genannten Datum ein Handler für `navigation_waypoints_request`; der dazugehörige [Pull Request 443](https://github.com/teslamotors/vehicle-command/pull/443) ist offen. Die bestehende TeslaTalk-Verbindung über `navigation_request` ist daher kein Nachweis für Mehrfachstopps. Die API-Dokumentation allein ersetzt den Test im Fahrzeug nicht.

## ABRP als zusätzliche Planungsquelle

Die [offizielle ABRP-API-Seite](https://abetterrouteplanner.com/resources/api) unterscheidet diese Wege:

| Weg | Nutzen für TeslaTalk | Voraussetzung / Grenze |
| --- | --- | --- |
| Deep Link zu ABRP | Start, Ziel, Fahrzeugmodell und Ladestand für eine Planung in ABRP vorbelegen | Ein ausgehender Link liefert keinen automatischen Rückimport der berechneten Ladehalte |
| OAuth mit `get_plan` | Einen vom Nutzer freigegebenen ABRP-Plan importieren | Freigabe/Anwendungszugang bei Iternio nötig; laut Anbieter gekürzter Plan, genaue Inhalte auf Anfrage klären |
| Planning API v2 | Gemeinsamen Ladeplan im Backend berechnen und strukturiert übernehmen | Separater API-Zugang, Einrichtungskosten und Preis pro Plan; ein kostenloser Telemetrie-Schlüssel ersetzt diesen Zugang nicht |
| Telemetry API | Mit Einwilligung aktuelle Fahrzeugwerte an ABRP liefern | Optional; Nutzer-Token nötig. Kein Ersatz für die Planning API |

ABRP unterstützt [Ladenetze bevorzugen oder vermeiden](https://abrp.featurebase.app/help/articles/4671857-avoid-and-prefer) und [Ladekarten](https://abrp.featurebase.app/help/articles/5884894-charge-cards). Damit kann die Planung beispielsweise andere Netze bevorzugen und Supercharger vermeiden. Restriktive Vorgaben können eine Route unmöglich machen; dann soll TeslaTalk die Vorgabe sichtbar melden und keine stillen Ausnahmen machen. Welche Filter die freigegebene API-Version anbietet, muss mit deren Schema geprüft werden.

## Empfohlener Ablauf für die Gruppe

1. Der Fahrtleiter sieht weiterhin ganz oben niedrigsten Akku und geringste gemeldete Reichweite. Das Fahrzeug mit der geringsten Reichweite ist die erste Empfehlung, die Auswahl bleibt ausdrücklich beim Fahrtleiter.
2. Zusätzlich werden das konkrete Fahrzeugmodell, aktueller Akku, Verbrauchsannahmen, Ladeanschluss und Reserve je Auto benötigt. Reichweite und Prozent allein reichen für eine belastbare Ladeplanung nicht.
3. Der Leiter wählt **Tesla-Planung** oder künftig **ABRP-Planung**, Ziel, bevorzugte/ausgeschlossene Netze und gewünschte Ankunftsreserve. Ein ABRP-Aufruf muss mit dem ausgewählten Fahrzeugmodell erfolgen, nicht mit einem beliebigen Standardmodell.
4. Die Planungsquelle liefert eine geordnete Liste gemeinsamer Stationen. Jeder Stopp bekommt Stations-ID, Namen, Koordinaten und Netz; je Fahrzeug werden erwarteter Ankunftsakku, nötiger Abfahrtsakku und Ladezeit gespeichert. Der Plan erhält eine Version, damit Rückmeldungen einem konkreten Plan zugeordnet werden.
5. Alle Abschnitte werden für jedes Gruppenfahrzeug geprüft. Das Auto mit der geringsten angezeigten Reichweite ist nicht zwangsläufig auf jedem Abschnitt das begrenzende Auto. Fehlende/veraltete Daten bleiben unbestätigt. Schafft ein Auto einen Abschnitt nicht, erhält der Leiter eine Meldung und einen Vorschlag zur gemeinsamen Neuplanung.
6. Erst nach Zustimmung der jeweiligen Besitzer geht dieselbe Stoppreihenfolge an alle Autos. Die App unterscheidet Befehl angenommen, Zwischenstopps im Auto bestätigt und Ladeziele geprüft. Automatische Tesla-Neuplanung darf nicht als Bestätigung identischer Ladehalte gelten.
7. Für die gemeinsame Weiterfahrt zählt die längste erforderliche Ladezeit. Fahrzeuge mit mehr Reserve dürfen weniger laden; die Gruppe wartet auf das begrenzende Fahrzeug. Gleiche Stationen garantieren weder freie Ladesäulen noch sekundengleichen Ladebeginn. Genügend passende Ladeplätze und die gemeinsame Abfahrt müssen separat berücksichtigt werden.

Falls vollständige Zwischenziellisten am Fahrzeug nicht zuverlässig unterstützt werden, ist eine mögliche Alternative: Den gesamten Plan in TeslaTalk anzeigen und jeweils **den nächsten gemeinsamen Ladestopp** als Ziel übertragen. Der Leiter gibt den nächsten Abschnitt frei. Diese Alternative muss sichtbar als abschnittsweise Navigation bezeichnet werden; sie ist noch nicht implementiert. Batterie-Vorkonditionierung bei per Koordinate gesendeten Fremdladern muss ebenfalls geprüft werden.

## Konfiguration und Betrieb

Ein ABRP-Zugang wäre serverseitig zu konfigurieren; Zugangsdaten gehören nicht in Links, Frontend oder LLM-Kopiertext. Ein ausgehender Deep Link würde Standort/Planungswerte an ABRP übermitteln und soll deshalb erst durch eine bewusste Nutzeraktion geöffnet werden. Nutzerspezifischer Planimport bzw. Telemetrie braucht eine getrennte ABRP-Einwilligung. Der Tesla-Login erteilt keine ABRP-Rechte.

ABRP-Aufrufe und Tesla-Befehle wären ausgehende HTTPS-Verbindungen. Dafür ist am VPS mit CGNAT/WireGuard keine neue eingehende Portweiterleitung nötig. Ein zusätzlicher signierender Command-Proxy sollte nur im internen Dienstnetz erreichbar sein.

## Akzeptanztests vor Freigabe der Integration

- [ ] Autorisierter ABRP-Plan liefert alle Ladehalte mit Reihenfolge und Koordinaten; ein bloßer Plan-Link reicht nicht.
- [ ] Gewünschte Fremdnetze erscheinen, ausgeschlossene Supercharger werden nicht stillschweigend wieder eingefügt.
- [ ] Alle Fahrzeuge schaffen jeden Abschnitt mit ihrer eigenen Reserve; veraltete/unbekannte Werte werden nicht als Zusage behandelt.
- [ ] Nach Zwischenstopp-Übertragung zeigt jedes echte Auto dieselbe Stoppreihenfolge; Mehrfachstopps ersetzen/ergänzen bestehende Navigation wie erwartet.
- [ ] Vorkonditionierung und Verhalten bei Tesla-Neuberechnung an Superchargern und Fremdladern prüfen.
- [ ] Widerruf, Fahrzeugwechsel und Fahrtende stoppen weitere Befehle; Fehler lösen keine wiederholten Sendeschleifen aus.
- [ ] Gruppenabfahrt richtet sich nach dem langsamsten nötigen Ladevorgang; nicht nur nach gleichen Ankunftszeiten.
