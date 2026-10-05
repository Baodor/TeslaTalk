# Komfortsteuerung für die Gruppe

Der Fahrtleiter findet die Fahrzeugsteuerung im Tab **Fahrzeugsteuerung** direkt neben **Verlauf**. Der Tab und die Gruppenknöpfe erscheinen nur für ihn. Andere Fahrer sehen auf der Karte ausschließlich **Freigabe meines Fahrzeugs**; der Leiter gibt sein eigenes Auto im Steuerungs-Tab frei. Die Steuerung ist nur während einer aktiven Fahrt verfügbar. Jeder Fahrer gibt sein eigenes aktuelles Auto separat frei; eine Routenfreigabe gilt dafür nicht. Die Freigabe kann jederzeit widerrufen werden und entfällt beim Fahrzeugwechsel. Tesla-verknüpfte Mitfahrer bleiben ausgeschlossen. Beim Tabwechsel bleiben Ergebnisse und unklare Aufträge erhalten; es wird kein Befehl erneut gesendet.

| Knopf | Verhalten |
| --- | --- |
| Frunk öffnen | Öffnet einen geschlossenen Frunk; geschlossen wird er von Hand |
| Heckklappe betätigen | Betätigt die Heckklappe entsprechend ihrer aktuellen Position; motorisiertes Schließen hängt vom Fahrzeug ab |
| Fenster lüften | Öffnet die Fenster in die Tesla-Lüftungsposition |
| Fenster schließen | Schließt die Fenster, soweit vom Fahrzeug unterstützt |
| Klima an | Startet Vorklimatisierung mit der im Fahrzeug eingestellten Temperatur |
| Klima aus | Beendet die Vorklimatisierung |

Der Bestätigungsdialog nennt die betroffenen Fahrzeuge. Das Ergebnis erscheint für jedes Auto einzeln. Kofferraum- und Fensterbefehle benötigen frisch abgerufene Parkdaten; fehlende oder ältere Daten werden nicht als Stillstand interpretiert. Eine Tesla-Bestätigung ist kein Nachweis der mechanischen Endposition. Es gibt keine Türverriegelung oder Entriegelung, kein automatisches Aufwecken und keine automatische Wiederholung eines Befehls.

## Signierte Fahrzeugbefehle einrichten

Die Funktion ist standardmäßig deaktiviert. Für echte Autos braucht sie Teslas [Vehicle Command Proxy](https://github.com/teslamotors/vehicle-command), die OAuth-Berechtigung `vehicle_cmds` und den [virtuellen Fahrzeugschlüssel](https://developer.tesla.com/docs/fleet-api/virtual-keys/developer-guide). Der öffentliche Schlüssel muss zu dem privaten Schlüssel des Proxys passen. Bei der vorhandenen Installation verwenden beide das mit `scripts/configure.py` erzeugte Schlüsselpaar.

1. In deiner Tesla-Fleet-Anwendung die Fahrzeugbefehlsberechtigung erlauben.
2. Im Projektverzeichnis als Eigentümer der vorhandenen Tesla-Schlüssel ausführen:

   ```bash
   python3 scripts/configure_vehicle_controls.py
   ```

   Das Skript erzeugt nur ein TLS-Schlüsselpaar für den internen Proxy. Bestehende Tesla-Schlüssel und `.env` bleiben erhalten. Bei erneutem Aufruf bleibt das noch gültige Zertifikat erhalten; es gilt ein Jahr. Vor Erneuerung beide TLS-Dateien sichern und bewusst entfernen, anschließend das Skript erneut ausführen und beide Container neu erstellen.

3. In `.env` setzen:

   ```dotenv
   TESLA_GROUP_CONTROLS=true
   TESLA_COMMAND_PROXY_USER=1000:1000
   ```

   `1000:1000` durch den **vom Skript ausgegebenen UID:GID-Wert** ersetzen. So kann der Proxy die privaten Dateien mit Modus `0600` lesen. Keine privaten Schlüssel mit `chmod 644` freigeben.

4. Den bestehenden Traefik-Stack mit dem zusätzlichen Overlay starten:

   ```bash
   docker compose -f compose.traefik.yaml -f compose.vehicle-controls.yaml up -d --build
   ```

   Der Proxy veröffentlicht keinen Host-Port und keinen Traefik-Router. TeslaTalk erreicht ihn über das interne Docker-Netzwerk mit geprüftem TLS-Zertifikat. CGNAT, WireGuard und die LiveKit-Medienports benötigen dafür keine zusätzlichen öffentlichen Freigaben. Künftige Aktualisierungen dieses Stacks verwenden wieder **beide** Compose-Dateien.

   Der Proxy verwendet `working_dir: /`, damit sein Arbeitsverzeichnis auch mit der UID des Schlüsselbesitzers erreichbar ist. Die allgemeine Tesla-Warnung bei Bindung an `0.0.0.0` erscheint weiterhin; sie bestätigt weder einen veröffentlichten Port noch einen erfolgreichen Fahrzeugbefehl.

5. Jeder Fahrer meldet sich erneut mit Tesla an, damit `vehicle_cmds` freigegeben wird. Der Fahrzeugschlüssel wird über `https://tesla.com/_ak/DEINE_TESLATALK_DOMAIN` in der Tesla-App für das gewünschte Fahrzeug installiert. Danach erlaubt jeder Fahrer die Komfortsteuerung in der aktiven Fahrt. Ohne Schlüssel/Freigabe erscheint ein Fehler statt einer behaupteten Ausführung.

Ein bereits vorhandener offizieller Proxy kann alternativ über `TESLA_COMMAND_PROXY_URL=https://...` eingebunden werden. Bei eigener CA ist `TESLA_COMMAND_PROXY_CA` der Pfad der eingebundenen Zertifikatdatei **im TeslaTalk-Container**. HTTPS und Zertifikatprüfung sind erforderlich. Das Overlay ist nur für die mitgelieferte interne Proxy-Variante nötig.

## Navigationsbefehle zusätzlich aktivieren

Die Zielübertragung hat einen eigenen Schalter: `TESLA_NAVIGATION_COMMANDS=true` in `.env` ergänzen und den Stack mit beiden Compose-Dateien neu erstellen. Anschließend erneut mit Tesla anmelden, damit `vehicle_cmds` im Konto freigegeben ist. Bei konfiguriertem Proxy geht auch `navigation_request` mit Zertifikatprüfung über diesen Proxy. Eine ungültige Proxy-Adresse wird abgelehnt; nach einem Proxyfehler erfolgt kein Wechsel auf die direkte Fleet API. Ohne eingerichteten Proxy bleibt der direkte Aufruf erhalten. Teslas offizieller Proxy leitet `navigation_request` selbst über REST weiter; dieser Befehl wird dadurch nicht in einen signierten Fahrzeugbefehl umgewandelt. Die Komfortbefehle benötigen weiterhin den virtuellen Fahrzeugschlüssel.

## Fehler und Auftragsstatus

Jede Aktion hat eine UUID. Dieselbe UUID mit denselben Daten liefert das gespeicherte Ergebnis zurück und betätigt kein Auto erneut. Eine laufende Gruppenaktion sperrt weitere Aufträge derselben Fahrt. Es werden höchstens sechs neue Aktionen pro Minute angenommen.

Bei unterbrochener Verbindung meldet die Oberfläche ein unklares Ergebnis und bietet **Auftragsstatus abrufen** an. Diese GET-Abfrage sendet keinen Befehl. Nach einem Serverneustart werden angefangene Aufträge als unklar abgeschlossen und niemals automatisch neu abgesendet. Eine bereits an Tesla gesendete Aktion lässt sich durch späteren Widerruf nicht zurückholen.

Im Demo-Modus werden alle Aktionen ausdrücklich als Simulation angezeigt. Automatisierte Tests verwenden simulierte Tesla-Antworten und steuern keine echten Autos. Die [Testcheckliste](TEST-CHECKLIST.de.md) beschreibt den anschließenden Test am Fahrzeug.
