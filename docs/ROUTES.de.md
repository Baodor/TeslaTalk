# Routenplanung in der Gruppe

TeslaTalk kann Ziele und importierte Ladepläne abschnittsweise verteilen. Der Tourleiter sendet jeweils den nächsten gemeinsamen Halt; jeder Tesla berechnet diesen Abschnitt selbst. Native vollständige Ladehaltefolgen werden nicht aus dem Tesla exportiert und die Vorkonditionierung wird nur nach sichtbarer Prüfung im Auto bestätigt. [Ladeplan-Import](CHARGING-PLANS.de.md).

## Ablauf

1. Alle Fahrer treten der aktiven Fahrt bei. Ganz oben zeigt die Routenübersicht die aktuellen Akkustände und gemeldeten Reichweiten. Zwei getrennte Empfehlungen markieren den niedrigsten Akku und die geringste Reichweite; Werte älter als fünf Minuten und unbekannte Werte werden ausgeschlossen.
2. Fahrer erlauben **Automatische Zielübernahme in meinem Auto** für ihr eigenes ausgewähltes Auto und diese Fahrt. Der Fahrtleiter kann ein anderes Auto erst nach dieser Zustimmung wählen. Mitfahrer haben keine Fahrzeugsteuerung.
3. Der Fahrtleiter gibt eine eindeutige Zieladresse ein und wählt das Planungsfahrzeug, vorzugsweise anhand der geringsten Reichweite. Vor dieser Auswahl wird keine Fahrerroute übernommen.
4. Dieses Auto bekommt das Ziel und berechnet seine Navigation. Eine bestätigte HTTP-Befehlsantwort bedeutet erst Zielannahme. Erst aktuelle Fahrzeugdaten bzw. Telemetrie liefern die berechnete Gruppenroute. Die Anzeige wird automatisch für berechtigte Teilnehmer aktualisiert.
5. Weitere zustimmende Fahrzeuge bekommen das Ziel. Ihr Tesla plant selbst; gleiche Ladehalte sind derzeit nicht bestätigt. Fehlgeschlagene Befehle erscheinen als Fehler und können vom Besitzer wiederholt werden. Es gibt keine automatische Befehls-Endlosschleife.
6. Bei einer erkannten Abweichung oder **Mein Auto schafft diese Route nicht** sieht der Fahrtleiter das betroffene Fahrzeug und erhält bei vorhandener Push-Einwilligung eine Meldung. Er kann dessen aktuelle Route als neue Referenz wählen. Das übernimmt den angezeigten Verlauf; an andere Autos geht weiterhin nur das Ziel.

## Datenquellen

| Information | Quelle / Grenze |
| --- | --- |
| Akku, geschätzte Reichweite | Zwischengespeicherte Tesla-/Telemetriewerte, Navigationsabfrage oder bewusster Datenabruf; Browser-GPS liefert diese Werte nicht |
| Live-Fahrzeugstandort | Ausschließlich Fahrer-Browser-GPS des ausgewählten Autos, kein Tesla-GPS-Fallback |
| Navigationsziel, Reststrecke, Restzeit, Akku bei Ankunft | `vehicle_data.drive_state.active_route_*`; Auto muss erreichbar sein, Felder können fehlen |
| Tatsächlicher Straßenverlauf | Separater Fleet-Telemetry-Stream mit `RouteLine`, in TeslaTalk über persönlichen API-Schlüssel importiert |
| Gemeinsame Ladehaltefolge | Geprüfter GPX-/TeslaTalk-JSON-Import; geordnete Liste in TeslaTalk, nächster Halt einzeln übertragbar. Keine automatische Extraktion aus Tesla RouteLine |
| Straßenvergleich | Mit aktuellen vollständigen Linien und vergleichbaren Startpunkten: geometrische Toleranz 200 m. Sonst unbestätigt; keine Garantie exakter Identität |

Eine Tesla-Anmeldung ist ein Berechtigungsnachweis, kein vollständiger Datenstream. TeslaTalk deployt noch keinen Fleet-Telemetry-Empfänger. Die [offiziellen Datenfelder](https://developer.tesla.com/docs/fleet-api/fleet-telemetry/available-data) beschreiben, welche Daten über Telemetrie und welche über `vehicle_data` kommen.

## Echte Zielbefehle aktivieren

- In der Tesla-Entwickleranwendung die Berechtigung `vehicle_cmds` freigeben.
- In `.env` `TESLA_NAVIGATION_COMMANDS=true` setzen und den App-Container neu erstellen.
- Vorhandene Tesla-Konten erneut verbinden, damit die Zustimmung den neuen Scope enthält. Akkudaten/Position können bereits mit den bisherigen Leserechten funktionieren.
- Je nach Fahrzeug die Anforderungen an den App-Fahrzeugschlüssel prüfen. Die [offiziellen Navigationsbefehle](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands) und [Scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview) sind die maßgeblichen Quellen.

Die App exponiert ausschließlich `navigation_request`, keine generische Fahrzeugbefehls-API. Schlafende Autos werden nicht geweckt. Befehle stoppen am Fahrtende oder bei Widerruf/Fahrzeugwechsel. Es werden keine echten Befehle bei den automatisierten Tests gesendet.

## Gemeinsame Ladehalte und ABRP

Unter **Gemeinsamer Ladeplan** kann der Fahrtleiter eine Datei hochladen und die Stationen prüfen. Bestehende Fahrerzustimmungen gelten auch für den nächsten gemeinsamen Halt. Der Importmodus bewahrt Stationsreferenzen und verhindert, dass normale Routenupdates diese durch reine Koordinaten ersetzen. Jeder Fahrer bestätigt Stationszuordnung und angezeigte Vorkonditionierung im eigenen Tesla. [Formate, Ablauf und Grenzen](CHARGING-PLANS.de.md).

Bei geöffneter privater Gruppe wird nur die Navigation zustimmender Autos mit Planungsfahrzeug standardmäßig alle 600 Sekunden abgerufen. Browserpositionen aktualisieren die Karte unabhängig davon. Ein manueller Routenabruf bleibt möglich.
