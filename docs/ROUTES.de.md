# Routenplanung in der Gruppe

Der gemeinsame Ladeablauf ist noch nicht vollständig implementiert: TeslaTalk überträgt aktuell Zieladressen, keine identischen Ladehalte. Diese Grenze wird auch in der Oberfläche und im API-Export angezeigt.

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
| Akku, geschätzte Reichweite, Standort | Normale Tesla Fleet API; nach Tesla-Login mit freigegebenen Datenrechten |
| Navigationsziel, Reststrecke, Restzeit, Akku bei Ankunft | `vehicle_data.drive_state.active_route_*`; Auto muss erreichbar sein, Felder können fehlen |
| Tatsächlicher Straßenverlauf | Separater Fleet-Telemetry-Stream mit `RouteLine`, in TeslaTalk über persönlichen API-Schlüssel importiert |
| Geplante vollständige Ladehaltefolge | Wird von dieser Integration nicht exportiert oder übertragen; `RouteLine` allein ersetzt diese Information nicht |
| Straßenvergleich | Mit aktuellen vollständigen Linien und vergleichbaren Startpunkten: geometrische Toleranz 200 m. Sonst unbestätigt; keine Garantie exakter Identität |

Eine Tesla-Anmeldung ist ein Berechtigungsnachweis, kein vollständiger Datenstream. TeslaTalk deployt noch keinen Fleet-Telemetry-Empfänger. Die [offiziellen Datenfelder](https://developer.tesla.com/docs/fleet-api/fleet-telemetry/available-data) beschreiben, welche Daten über Telemetrie und welche über `vehicle_data` kommen.

## Echte Zielbefehle aktivieren

- In der Tesla-Entwickleranwendung die Berechtigung `vehicle_cmds` freigeben.
- In `.env` `TESLA_NAVIGATION_COMMANDS=true` setzen und den App-Container neu erstellen.
- Vorhandene Tesla-Konten erneut verbinden, damit die Zustimmung den neuen Scope enthält. Akkudaten/Position können bereits mit den bisherigen Leserechten funktionieren.
- Je nach Fahrzeug die Anforderungen an den App-Fahrzeugschlüssel prüfen. Die [offiziellen Navigationsbefehle](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands) und [Scopes](https://developer.tesla.com/docs/fleet-api/authentication/overview) sind die maßgeblichen Quellen.

Die App exponiert ausschließlich `navigation_request`, keine generische Fahrzeugbefehls-API. Schlafende Autos werden nicht geweckt. Befehle stoppen am Fahrtende oder bei Widerruf/Fahrzeugwechsel. Es werden keine echten Befehle bei den automatisierten Tests gesendet.

## Gleiche Ladehalte und ABRP

Tesla dokumentiert `navigation_waypoints_request` für eine Zwischenzielliste. Der in der Tesla-App sichtbare Ladeplan ist über die hier verwendeten öffentlichen Lesefelder jedoch nicht als vollständige Liste dokumentiert. Ladenetz-Auswahl und ein eigener gemeinsamer Ladeplan über ABRP sind mögliche nächste Schritte. [CHARGING-PLANS.de.md](CHARGING-PLANS.de.md) trennt die vorhandenen Funktionen vom Integrationsentwurf, erläutert die Kosten/Zugänge und enthält Tests für die tatsächliche Zwischenstopp-Übertragung.

## API und Tests

Die Endpunkte und der vollständige LLM-Kopiertext stehen unter **Mein Profil → Persönliche API-Schlüssel → Alle API-Endpunkte & LLM-Kopierfunktion**. Details zum Telemetrieimport enthält [API.md](API.md); manuelle Prüfung am Server und Auto: [Testcheckliste](TEST-CHECKLIST.de.md).
