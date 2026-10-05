# Testcheckliste: Konten, Fahrzeugnavigation und API-Dokumentation

Nach dem Update mit einem Fahrer-Konto testen. Die automatisierten Tests verwenden isolierte Daten, simulierte Tesla-Antworten und Demo-Fahrzeuge. Der tatsächliche Abruf aus einem physischen Tesla muss an der eigenen Installation geprüft werden.

## Komfortsteuerung, Karten und neue Kontofunktionen

- [ ] [Signierten Proxy einrichten](VEHICLE-CONTROLS.de.md), Tesla-Konten mit `vehicle_cmds` erneut verbinden und virtuellen Schlüssel installieren. Ohne Aktivierung sind die Komfortknöpfe gesperrt; reine Fahrzeugdaten bleiben nutzbar.
- [ ] In einer aktiven Fahrt erlaubt jeder Fahrer **Komfortsteuerung für mein Auto** separat. Routenübernahme allein erlaubt keine Komfortsteuerung. Der Fahrtleiter öffnet **Fahrzeuge steuern** und sieht die freigegebenen Autos.
- [ ] **Klima an** und **Klima aus** getrennt bestätigen: Empfängerliste stimmt, alle freigegebenen Fahrzeuge reagieren, nicht freigegebene Autos bleiben unberührt. Temperatur ist die im jeweiligen Auto eingestellte Temperatur.
- [ ] Im Stand/Parkstellung bei freien beweglichen Teilen Frunk, Heckklappe sowie Fenster lüften/schließen einzeln testen. Frunk manuell schließen. Unbekannte Parkdaten verhindern Kofferraum-/Fensterbefehle; kein Türverriegeln/Entriegeln vorhanden.
- [ ] Bestätigungsdialog abbrechen: kein Befehl. Schlafendes/unerreichbares Auto verursacht nur einen eigenen Fehler und wird nicht geweckt. Verbindung unterbrechen: **Auftragsstatus abrufen** sendet keinen zweiten Befehl. Tatsächlichen Zustand am Auto prüfen.
- [ ] Freigabe widerrufen, Fahrzeug wechseln und Fahrt beenden: keine weiteren Komfortbefehle an das bisher freigegebene Auto. Ein Tesla-verknüpfter Mitfahrer erscheint nicht in der Fahrzeugsteuerung oder Akku-/Reichweitenplanung.
- [ ] QR-Mitfahrer verbindet in **Mein Profil** sein Tesla-Konto: Bild erscheint, Name/PIN und Mitfahrerrolle bleiben. Nach Abmelden über denselben QR-Link anmelden; Bild bleibt. Verknüpfung entfernen: PIN funktioniert weiter, kein Fahrzeugzugriff.
- [ ] Im Adminmenü mit einem eigens angelegten Testkonto **Löschen** wählen. Falsche Groß-/Kleinschreibung im Bestätigungsnamen hält den Knopf gesperrt; Abbrechen löscht nichts. Erst mit exaktem Namen bestätigen. Konto und eigene geleitete Testfahrten verschwinden, seine alten Sitzungen/API-Schlüssel funktionieren nicht mehr, fremde Fahrten bleiben bestehen.
- [ ] Logo aus Profil/Fahrt/Admin anklicken: Startseite. Mac/Safari neu laden und Desktop-Favicon prüfen; gegebenenfalls alten Safari-Favicon-Cache abwarten. Auf dem Arbeitsplatz-PC OSM-Karte prüfen: bei Netzwerksperre verständliche Fehlermeldung und erneutes Laden. Der Referrer enthält nur die Domain, keinen Fahrtpfad.
- [ ] **ABRP noch nicht als erfolgreichen Import testen:** Für normale Teilen-Links ist der gespeicherte Planabruf noch nicht integriert. Ein konkreter Beispiel-Link und ein verifizierter Abrufvertrag bzw. freigegebener Iternio-Zugang sind für diesen nächsten Schritt nötig.

## Tesla-Erstanmeldung und Administration

- [ ] Neu mit Tesla anmelden: vor den Fahrerfunktionen erscheint die Benutzernamenwahl. Namen mit 3–30 erlaubten Zeichen wählen; „Max“ und „max“ dürfen nicht getrennt vergeben werden. Ein belegter Name zeigt eine Fehlermeldung und lässt die Auswahl offen.
- [ ] Nach erfolgreicher Wahl, Seitenreload und erneuter Tesla-Anmeldung erscheint die Abfrage nicht mehr. Anzeigename/Kennzeichen bleiben erhalten. Bestehende selbst gewählte Namen werden beim Update nicht zurückgesetzt.
- [ ] Älteres Tesla-Konto mit automatisch erzeugtem Namen wird zur Auswahl aufgefordert. Demokonten und Mitfahrer brauchen diese Tesla-Ersteinrichtung nicht.
- [ ] Im OIDC-Adminmenü **Alle Benutzer** öffnen: Tesla-Mail, Benutzername, Kennzeichen, Profilbild und zuletzt erfassten Login vergleichen. Fehlende Bilder zeigen Initialen; alte unbekannte Loginzeiten zeigen „Noch nicht erfasst“.
- [ ] Nach einer echten erneuten Anmeldung und **Aktualisieren** ist der Loginzeitpunkt neu; gewöhnliche Seitenaufrufe ändern ihn nicht. Fahrer-/Mitfahrersitzung oder persönlicher API-Schlüssel allein darf `/api/admin/users` nicht lesen.

## Mitfahrer registrieren sich über QR

- [ ] Fahrtleiter zeigt unter **Fotos & Mitfahrer** den QR-Code. In einem zweiten Browser/Handy scannen, **Neu registrieren**, Namen und eigenen sechsstelligen PIN zweimal eingeben. Führende Null testen; unterschiedliche Bestätigung verhindert die Registrierung.
- [ ] Erfolgreiche Registrierung öffnet direkt die Fahrt; Name erscheint sofort in Teilnehmerliste und Mitfahrerübersicht des Fahrtleiters. Es muss vorher kein Name/PIN durch den Leiter angelegt werden.
- [ ] Abmelden und denselben QR-Link öffnen: **Bereits registriert? Anmelden**, Name/PIN eingeben. Derselbe Mitfahrer kehrt zurück; keine zusätzliche Identität. Falscher PIN wird abgelehnt.
- [ ] Ein bereits verwendeter Name, auch mit anderer Groß-/Kleinschreibung, darf durch Registrierung mit neuem PIN nicht übernommen werden. Stattdessen anmelden oder einen anderen Namen wählen.
- [ ] Vor Fahrtbeginn und nach Ende sind Registrierung/Anmeldung gesperrt. Mitfahrer können Standort und Chat nutzen, aber keine Fahrzeuge auswählen/steuern, API-Schlüssel erstellen oder Admin-Benutzerdaten abrufen.

## Navigation im echten Auto

- [ ] Im wachen Auto eine Navigation starten. Unter **Mein Profil → Route aus deinem Auto → Route aus Auto abrufen** Zielname, Zielkoordinaten, Reststrecke, Restzeit und Akku bei Ankunft mit dem Auto vergleichen. Nicht verfügbare Felder bleiben leer.
- [ ] Ohne aktives Ziel erneut abrufen (gegebenenfalls den 60-Sekunden-Cache abwarten). Die App meldet keine aktive Navigation; das alte Ziel wird nicht weiter angezeigt.
- [ ] Bei fehlenden Tesla-Daten oder einem schlafenden Auto erscheint eine verständliche Meldung. Das Auto wird nicht automatisch geweckt.
- [ ] Alle Fahrer der aktiven Fahrt beitreten lassen. Vor Fahrzeugauswahl bleibt die Gruppenroute leer; ganz oben stehen **geringste Reichweite** und **niedrigster Akkustand** als getrennte Empfehlungen. Unterschiedliche Fahrzeugwerte testen, unbekannte Werte und Werte älter als fünf Minuten werden ausgeschlossen.
- [ ] Jeder Fahrer erlaubt **Automatische Zielübernahme in meinem Auto**. Der Fahrtleiter gibt eine eindeutige Zieladresse an und wählt genau das gewünschte Planungsfahrzeug. Ein anderes Auto ohne Zustimmung darf nicht gewählt werden.
- [ ] Das gewählte Auto erhält zuerst das Ziel. Erst seine aktuelle Navigation erscheint automatisch als Gruppenroute; danach bekommen weitere zustimmende Autos das Ziel. Autos ohne Zustimmung bleiben unberührt. Den Demoablauf getrennt vom echten Fahrzeug testen.
- [ ] Bei echten Autos vorab `TESLA_NAVIGATION_COMMANDS=true`, `vehicle_cmds` in der Tesla-Anwendung und erneute Kontoanmeldung prüfen. Ohne Befehlsberechtigung verständliche Meldung; reine Fahrzeugdaten bleiben nutzbar.
- [ ] Als Teilnehmer fehlt die Auswahlfunktion des Fahrtleiters. Zielübernahme widerrufen und danach Zielwechsel testen: keine neuen Zielbefehle an dieses Auto. Sichtbarkeit der Gruppenroute bleibt automatisch.
- [ ] **Mein Auto schafft diese Route nicht** melden. Fahrtleiter sieht das betroffene Auto und kann dessen aktuelle Route als neue Referenz wählen. Bei aktivierten Benachrichtigungen kommt eine Meldung, wiederholte gleiche Probleme werden nicht mehrfach gepusht.
- [ ] Auto wechseln: die Zustimmung wird für das bisherige Auto entfernt. Wurde dieses Auto als Planungsfahrzeug gewählt, muss erneut ausgewählt werden; keine stillschweigende Übernahme des neuen Autos.
- [ ] Fahrt beenden: keine weiteren Fahrzeugbefehle/Live-Routenupdates, Mitfahrer verlieren Zugang, letzter Routenstand bleibt für berechtigte Fahrer archiviert. Öffentlicher Leselink enthält keine Navigation.

**Grenze:** Zielübernahme bestätigt keine identische Route oder identische Ladehalte. Die App muss diese Grenze sichtbar nennen; gemeinsames gleichzeitiges Laden ist damit noch nicht garantiert.

## Genaue Linie mit bestehender Fleet-Telemetry-Integration

- [ ] Falls eine Integration vorhanden ist: vollständigen Snapshot mit `RouteLine` per persönlichem Bearer an `PUT /api/vehicles/{vehicle_id}/navigation` schicken. Die Linie folgt dem tatsächlichen Straßenverlauf; Koordinaten sind Polyline6, nicht Polyline5.
- [ ] Neue Linie/anderes Ziel bzw. `active:false` importieren. Freigegebene aktive Fahrt aktualisiert/entfernt die Linie. Ein Snapshot ohne `route_line` zeigt keine alte Linie weiter. Ohne Linien und bei verschiedenen Startpunkten bleibt der Vergleich unbestätigt.
- [ ] Ungültige/abgeschnittene Linie oder zu alter Zeitpunkt ergibt 422. Gleicher/älterer Telemetriezeitpunkt ergibt 409. Cookie ohne API-Schlüssel ergibt 403; fremdes Fahrzeug ergibt 404.

Ohne diese Integration zeigt `vehicle_data` Ziel und Kennzahlen, keinen vollständigen Straßenverlauf. Der reine private Abruf sendet keine Fahrzeugbefehle. Für eine bereits ausgewählte Gruppenroute kann eine Aktualisierung dagegen die erlaubte Zielübernahme auslösen.

## API-Seite und Kopierfunktion

- [ ] **Mein Profil → Persönliche API-Schlüssel → Alle API-Endpunkte & LLM-Kopierfunktion** öffnet `/api-docs`.
- [ ] HTTP-Methode, Pfad, Funktion, Zugriffsrechte und Anfrage-/Antwortschemas kontrollieren; auch Auth-Callbacks, Navigation und WebSocket sind gelistet.
- [ ] Suche/Filter setzen und **Alle Informationen für ein LLM kopieren** antippen. Im eingefügten Text müssen trotzdem alle Endpunkte, Regeln, Beispiele und JSON-Schemas enthalten sein.
- [ ] Kopieren in der installierten iPhone-PWA und am Desktop prüfen. Falls der Browser es ablehnt, den vollständigen manuellen Kopiertext bzw. **Text herunterladen** nutzen.
- [ ] Im Kopiertext stehen Platzhalter; eigener tatsächlicher API-Schlüssel, Sitzung, Kennzeichen, VIN, Fahrt-PIN und private Fahrzeugdaten fehlen. Neue Planungs-/Übernahme-/Problemendpunkte und die Ladehalte-Grenze sind im Kopiertext enthalten.
- [ ] Ohne Anmeldung liefern `/api/docs` und `/api/openapi.json` 401; die Seite zeigt einen Anmeldelink. Ein gültiger persönlicher Bearer darf die Dokumentation lesen, keine Adminaktionen ausführen.
- [ ] Smartphone im Hochformat: kein horizontales Seitenüberlaufen, Knöpfe und Eingaben gut bedienbar.

## Kurzer Regressionstest

- [ ] Chat und gemeinsame Karte mit zwei Fahrern; persönlicher Standort bleibt von der Fahrzeugposition getrennt.
- [ ] Sprachfunk mit zwei gleichzeitig geöffneten Mikrofonen über Mobilfunk; bei CGNAT die vorhandenen VPS-Weiterleitungen 7881/TCP und 7882/UDP weiter nutzen.
- [ ] Persönlichen Benachrichtigungstest aus der installierten Handy-PWA senden, PWA schließen/Handy sperren und Eingang prüfen. Providerannahme und tatsächliche Geräteanzeige getrennt beurteilen.

Diese Checkliste ergänzt automatisierte Backend-, Browser- und Containerprüfungen. Bei künftigen Änderungen werden passende manuelle Testpunkte im Abschluss mit angegeben.
