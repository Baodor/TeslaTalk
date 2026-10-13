# Testcheckliste: Konten, Fahrzeugnavigation und API-Dokumentation

Nach dem Update mit einem Fahrer-Konto testen. Die automatisierten Tests verwenden isolierte Daten, simulierte Tesla-Antworten und Demo-Fahrzeuge. Der tatsächliche Abruf aus einem physischen Tesla muss an der eigenen Installation geprüft werden.

## Komfortsteuerung, Karten und neue Kontofunktionen

- [ ] [Signierten Proxy einrichten](VEHICLE-CONTROLS.de.md), Tesla-Konten mit `vehicle_cmds` erneut verbinden und virtuellen Schlüssel installieren. Ohne Aktivierung sind die Komfortknöpfe gesperrt; reine Fahrzeugdaten bleiben nutzbar.
- [ ] In einer aktiven Fahrt erlaubt jeder Fahrer **Komfortsteuerung für mein Auto** separat. Andere Fahrer finden die eigene Freigabe auf der Karte; der Fahrtleiter im Tab **Fahrzeugsteuerung** neben **Verlauf**. Nur der Fahrtleiter sieht diesen Tab und die Gruppenknöpfe. Routenübernahme allein erlaubt keine Komfortsteuerung.
- [ ] Nach einer Aktion zu Karte/Chat wechseln: Steuerung ist ausgeblendet. Zurück zu **Fahrzeugsteuerung**: Ergebnisse und unklare Aufträge bleiben erhalten, kein zusätzlicher Befehl. Als Mitfahrer sind weder der Tab noch die eigene Fahrzeugfreigabe sichtbar.
- [ ] Proxy nach dem Update neu erstellen: kein **Could not get working directory** im neuen Container. Die allgemeine Tesla-Warnung zur Netzwerkbindung bleibt. Internes TLS prüfen; das ist noch kein Nachweis einer Fahrzeugausführung.
- [ ] **Klima an** und **Klima aus** getrennt bestätigen: Empfängerliste stimmt, alle freigegebenen Fahrzeuge reagieren, nicht freigegebene Autos bleiben unberührt. Temperatur ist die im jeweiligen Auto eingestellte Temperatur.
- [ ] Im Stand/Parkstellung bei freien beweglichen Teilen Frunk, Heckklappe sowie Fenster lüften/schließen einzeln testen. Frunk manuell schließen. Unbekannte Parkdaten verhindern Kofferraum-/Fensterbefehle; kein Türverriegeln/Entriegeln vorhanden.
- [ ] Bestätigungsdialog abbrechen: kein Befehl. Schlafendes/unerreichbares Auto verursacht nur einen eigenen Fehler und wird nicht geweckt. Verbindung unterbrechen: **Auftragsstatus abrufen** sendet keinen zweiten Befehl. Tatsächlichen Zustand am Auto prüfen.
- [ ] Freigabe widerrufen, Fahrzeug wechseln und Fahrt beenden: keine weiteren Komfortbefehle an das bisher freigegebene Auto. Ein Tesla-verknüpfter Mitfahrer erscheint nicht in der Fahrzeugsteuerung oder Akku-/Reichweitenplanung.
- [ ] QR-Mitfahrer verbindet in **Mein Profil** sein Tesla-Konto: Bild erscheint, Name/PIN und Mitfahrerrolle bleiben. Nach Abmelden über denselben QR-Link anmelden; Bild bleibt. Verknüpfung entfernen: PIN funktioniert weiter, kein Fahrzeugzugriff.
- [ ] Im Adminmenü mit einem eigens angelegten Testkonto **Löschen** wählen. Falsche Groß-/Kleinschreibung im Bestätigungsnamen hält den Knopf gesperrt; Abbrechen löscht nichts. Erst mit exaktem Namen bestätigen. Konto und eigene geleitete Testfahrten verschwinden, seine alten Sitzungen/API-Schlüssel funktionieren nicht mehr, fremde Fahrten bleiben bestehen.
- [ ] Logo aus Profil/Fahrt/Admin anklicken: Startseite. Mac/Safari neu laden und Desktop-Favicon prüfen; gegebenenfalls alten Safari-Favicon-Cache abwarten. Auf dem Arbeitsplatz-PC OSM-Karte prüfen: bei Netzwerksperre verständliche Fehlermeldung und erneutes Laden. Der Referrer enthält nur die Domain, keinen Fahrtpfad.
- [ ] ABRP-Excel-Export oder GPX/CSV mit benannten Stopps und Koordinaten lässt sich prüfen und speichern; reine Tracks werden abgewiesen. TeslaTalk-JSON exportieren und wieder hochladen: Reihenfolge, Stationstyp und vorhandene Places-ID bleiben erhalten. ABRP-Teilen-Links können im Reiter Ladeplanung mit verbundenem Konto als ursprüngliche Planungsparameter abgerufen werden; die neue Berechnung bleibt ein eigener Schritt.

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
- [ ] Bei echten Autos vorab `TESLA_NAVIGATION_COMMANDS=true`, `vehicle_cmds` in der Tesla-Anwendung und erneute Kontoanmeldung prüfen. Bei konfiguriertem Proxy geht die Zielübertragung ebenfalls darüber; Teslas Proxy behandelt `navigation_request` als REST-Weiterleitung. Ohne Befehlsberechtigung verständliche Meldung; reine Fahrzeugdaten bleiben nutzbar.
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

- [ ] Alle Gruppenmitglieder sehen aktuelle Fahrer-Browserpositionen. Fahrerbrowser schließen: keine automatische Tesla-GPS-Abfrage; Marker nach 90 Sekunden grau und nach fünf Minuten weg. Gruppenansicht folgt mehreren Autos, Eigenansicht dem eigenen Marker; manuelles Verschieben pausiert das Folgen kurz. Ohne private Gruppenverbindung erfolgt keine Navigationsabfrage.
- [ ] **Klima an/aus** funktioniert unabhängig vom Standort-/Parkdatenabruf. Falls der Befehl weiterhin scheitert, das Ergebnis pro Fahrzeug prüfen: Demo, HTTP-Code/Berechtigung, schlafendes Auto oder unklarer Ausgang. TLS-Verbindung und aktivierte Flags allein bestätigen keinen Fahrzeugbefehl. Kein automatischer Wiederholungsversuch.
- [ ] Chat und gemeinsame Karte mit zwei Fahrern; persönlicher Standort bleibt von der Fahrzeugposition getrennt.
- [ ] Sprachfunk mit zwei gleichzeitig geöffneten Mikrofonen über Mobilfunk; bei CGNAT die vorhandenen VPS-Weiterleitungen 7881/TCP und 7882/UDP weiter nutzen.
- [ ] Persönlichen Benachrichtigungstest aus der installierten Handy-PWA senden, PWA schließen/Handy sperren und Eingang prüfen. Providerannahme und tatsächliche Geräteanzeige getrennt beurteilen.

Diese Checkliste ergänzt automatisierte Backend-, Browser- und Containerprüfungen. Bei künftigen Änderungen werden passende manuelle Testpunkte im Abschluss mit angegeben.

## Browser-GPS, Zuschauer und Toilettenpause

- [ ] Zwei Fahrer erlauben Handy-GPS in einer aktiven Fahrt: beide Autos werden live angezeigt. Mitfahrer-GPS erscheint als Personenmarker; Akkudaten werden durch Browser-GPS nicht überschrieben.
- [ ] **Gruppe / Ich / Aus** testen, Karte kurz verschieben, Fahrer-GPS stoppen, Handy sperren und erneut öffnen: veraltete Positionen werden erkennbar und frische Updates setzen wieder ein. Keine kostenpflichtige Tesla-GPS-Ausweichabfrage.
- [ ] Zuschauerlink erstellen, ohne Anmeldung öffnen und auf einem zweiten Gerät verfolgen. Keine Chats, Kennzeichen, Tesla-Bilder oder Mitfahrerpositionen. Erneuern/Widerrufen/Fahrtende machen alte Links unbrauchbar.
- [ ] Bei allen Teilnehmern **Hinweistöne aktivieren**. Mitfahrer klickt Toilettenknopf: nur Fahrtleiter bekommt Bedarfston und Bestätigungsknopf. Zweimalige gleiche Anfrage erzeugt keine doppelten Hinweise.
- [ ] Fahrtleiter bestätigt Abfahrt: sichtbarer Hinweis in jedem Tab, gespeicherte Chatnachricht und genau ein Ton pro Gerät. Neue spätere Anfrage bleibt offen. Push zusätzlich mit gesperrtem iPhone/Android und erlaubten Mitteilungen testen; Fokusmodus berücksichtigen.

## Importierte Ladehalte

- [ ] GPX mit benannten Supercharger-/Fremdlader-Stopps hochladen. Vorschau/Stationsarten korrigieren; Speichern sendet keine Befehle. Reiner Track wird klar abgewiesen. JSON exportieren und identisch wieder importieren.
- [ ] Nur ein zweiter Fahrer erlaubt Zielübernahme. Tourleiter sendet Ladehalt: nur freigegebene aktuelle Fahrzeuge erhalten ihn. Dasselbe Ziel nach gewöhnlichem Routenupdate behält seine Stationsreferenz; es wird nicht automatisch erneut gesendet.
- [ ] An jedem echten Tesla prüfen, ob die konkrete Station als **Ladestation** erkannt wird und ob **Vorkonditionierung** angezeigt wird. Erst dann entsprechende Rückmeldung setzen; fehlende Erkennung bleibt unbestätigt. Sowohl Supercharger als auch mindestens einen unterstützten Fremdlader testen.
- [ ] Nächsten Halt senden, Stationsanzeige erneut prüfen. Plan-/Fahrzeugwechsel entfernt alte Bestätigungen. Nicht freigegebene Fahrzeuge, Mitfahrer, Zuschauer und beendete Fahrten können keine Befehle senden.
- [ ] Verbindung beim Senden unterbrechen: Auftragsstatus lesen und Auto prüfen, keine automatische Doppelübertragung. Danach ausdrücklich erneut freigeben, wenn ein weiterer Versuch gewünscht ist.

- [ ] Einen echten aktuellen ABRP-Excel-Export hochladen: benannte Stationen, Reihenfolge und Koordinaten/Stationslinks prüfen. Fehlen Koordinaten, Latitude/Longitude-Spalten ergänzen. Nicht enthaltene Stationen/Referenzen werden nicht erfunden. Excel mit mehreren Routentabellen oder übergroßen entpackten Daten wird abgewiesen.

## Tesla-Anmeldung und direkter ABRP-Reiter

- [ ] Tesla-Anmeldung aus installierter iPhone-Web-App über die öffentliche Domain abschließen; anschließend PWA neu öffnen. Kein roher JSON-Fehler. Anmeldung über eine alternative Adresse/LAN-IP startet zuerst auf der konfigurierten öffentlichen Domain.
- [ ] Zwei Tesla-Anmeldungen parallel beginnen und beide Rücksprünge testen; sie überschreiben ihre Bindungen nicht. Abgelaufener oder in anderem Browser geöffneter Rücksprung zeigt Neustart-Link mit korrekten Umlauten. Bereits angemeldeter alter Rücksprung führt ohne neuen Codeaustausch nach Hause.
- [ ] **Ladeplanung** ist ein eigener Reiter. Ohne Iternio-Key kostenlose Link-/QR-Übergabe und Dateiimport verfügbar. Die optionale API bleibt separat. Mit gültigem Planning-Key dort ABRP verbinden, genaue Fahrzeugvariante laden; gespeicherte/angezeigte Daten enthalten kein Passwort oder Token.
- [ ] Fahrzeug mit geringster Reichweite wählen, Abfahrtsakku prüfen, Start/Ziel und Zwischenhalt samt Aufenthalt setzen. Zwei Netze wie IONITY/EnBW auswählen und **Ausschließlich** aktivieren. Eine unmögliche Netzvorgabe wird gemeldet.
- [ ] ABRP-Linkparameter übernehmen: kein `/plan`-Aufruf, Hinweise zur Neuberechnung sichtbar. Erst nach Kostenbestätigung berechnen; Karte, Stoppreihenfolge und Prognosen für das Planungsauto prüfen.
- [ ] Berechnete Route prüfen und speichern: noch kein Fahrzeugbefehl. Danach nächsten gemeinsamen Ladehalt an die freigegebenen Autos senden. Im Tesla Stationszuordnung und Vorkonditionierung prüfen, einschließlich mindestens eines Fremdladers.
- [ ] Netzverbindung beim Berechnen unterbrechen, Reiter wechseln und Status abrufen: keine automatische zweite Berechnung. Bewusste neue Berechnung verlangt erneute Kostenbestätigung; Tageslimit wird eingehalten.
- [ ] ABRP-Verbindung entfernen/ablaufen lassen: gespeicherte Pläne bleiben sichtbar, geschützter Link-/Modellabruf verlangt erneute Verbindung. Andere Fahrer/Mitfahrer/Zuschauer können nicht im Namen des Leiters planen oder senden.


## Kostenfreie ABRP-Übergabe

- [ ] Ohne `ABRP_PLANNING_API_KEY` als Fahrtleiter **Ladeplanung** öffnen: Gruppenfahrzeug, gecachter Akku und Reichweite sichtbar; kein Katalog-/Login-/Planaufruf an Iternio. Keine zusätzlichen Tesla-Abrufe.
- [ ] Empfehlungen prüfen, Gruppenfahrzeug wechseln: Akku passt zum ausgewählten Auto. Alter/fehlender Akku wird geprüft oder manuell übernommen, nicht als Livewert dargestellt.
- [ ] Mit frischem Browserstandort Start setzen, Ziel und Zwischenstopp angeben, Übermittlung bestätigen: Link und QR enthalten die richtigen geordneten Routenpunkte. Ungültige Koordinaten werden abgewiesen. Nach einer Eingabeänderung verschwindet der alte Link/QR.
- [ ] Link am Handy und QR auf einem zweiten Gerät testen: ABRP übernimmt Start/Ziel/Zwischenstopps. Bei Adressproblemen Koordinaten einsetzen. Das passende gespeicherte ABRP-Fahrzeug auswählen und den Akku aus TeslaTalk mit dem Kopierknopf übernehmen; keine automatische SoC-/Kontoverknüpfung behauptet.
- [ ] Echte Anmeldung in ABRP mit **Login mit ABRP-App** und **Login remote app** durchführen. Der Login-QR kommt von ABRP, der TeslaTalk-QR öffnet die Route. Keine ABRP-Zugangsdaten in TeslaTalk nötig.
- [ ] In ABRP die eigenen Ladekarten, bevorzugten Netze und Fremdlader prüfen, dort berechnen, nach Excel exportieren und in TeslaTalk hochladen. Stoppkarte, Reihenfolge und Stationsreferenzen vor dem Speichern prüfen.
- [ ] Ladehalt an freigegebene Gruppenfahrzeuge senden und Stationszuordnung/Vorkonditionierung in den Teslas prüfen. Andere Fahrer/Mitfahrer/Zuschauer sehen keine Planungs-/Sendeknöpfe.
- [ ] Optionale kostenpflichtige API bleibt geschlossen. Auch Öffnen oder Scannen des kostenlosen Links löst keinen TeslaTalk-Planning-Auftrag aus. ABRP Premium-Funktionen hängen weiterhin vom eigenen ABRP-Konto ab.
