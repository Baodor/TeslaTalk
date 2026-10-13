# Browserstandort, Zuschauer und Pausen

## Standort ohne Tesla-GPS-Abfragen

1. In der aktiven Fahrt wählt jeder Fahrer sein Auto und erlaubt den Standortzugriff im Handy-/Fahrzeugbrowser. Fahrer-GPS ist zunächst eingeschaltet; der Knopf **Standort stoppen** beendet die Freigabe. Die Auswahl bleibt auf diesem Gerät für diese Fahrt gespeichert. Ein PC ohne brauchbares GPS ist keine geeignete Fahrzeugquelle.
2. Das eigene ausgewählte Auto erhält die Browserposition. Mitfahrer können optional ihren persönlichen Standort teilen, haben aber keine Fahrzeugrechte. Zwei Geräte eines Fahrers werden nach dem jüngsten echten Messzeitpunkt behandelt.
3. GPS-Messwerte werden höchstens alle zehn Sekunden übertragen. Die App fragt bei unveränderter Position weiterhin nach frischen Messwerten. Es gibt keinen automatischen Tesla-GPS-Fallback und keine erfundenen Akkudaten.
4. Auf der Karte **Gruppe**, **Ich** oder **Aus** wählen. Manuelles Verschieben/Zoomen pausiert das Folgen kurz. Nach 90 Sekunden ohne frischen Messwert wird ein Auto grau; nach fünf Minuten wird seine Live-Position entfernt. Aufgezeichnete Fahrthistorie bleibt privat.

Die Seite braucht HTTPS und muss geöffnet bleiben. Bildschirm-Wake-Lock wird angefragt, wenn der Browser es anbietet. Ein gesperrtes Handy oder eine Hintergrund-App kann GPS trotzdem aussetzen; eine PWA garantiert keinen dauerhaften Hintergrundstandort. Bei fehlender Berechtigung wird das angezeigt. Route und Stationsplanung sind weiterhin Fahrzeugdaten: `NAVIGATION_POLL_INTERVAL=600` (mindestens 60 Sekunden) reduziert automatische Routenabrufe; explizite Abfragen und Befehle können weiterhin kostenpflichtig sein. Polling erfolgt nur in aktiven privaten Gruppen mit Planungsauto und für zugestimmte aktuelle Fahrzeuge.

## Live-Zuschauerlink

Der Fahrtleiter öffnet **Zuschauerlink → Zuschauerlink erstellen** und teilt den Link oder QR-Code. Er kann schon vor Beginn erstellt werden; bis zum Start werden keine Positionen gezeigt. Während der Fahrt können Zuschauer die freigegebenen Fahrerpositionen, Anzeigenamen, Fahrzeugnamen/-modell, Fahrttitel und Ziel sehen. Mitfahrer-GPS, Chat, Kennzeichen, Tesla-Profilbilder, VIN, Konto-IDs und Historie werden nicht veröffentlicht.

Jeder mit dem Link kann diese freigegebenen Informationen lesen. Er erlaubt keine Gruppenmitgliedschaft oder Steuerung. **Erneuern** macht den vorherigen Link ungültig, **Widerrufen** beendet ihn sofort. Am Fahrtende endet auch die Zuschaueransicht. Zuschauerabrufe lesen vorhandene Browserpositionen alle zehn Sekunden und verursachen keine Tesla-Abfrage.

## Toilettenpause

Alle aktiven Teilnehmer haben **Ich muss aufs Klo**. Der Fahrtleiter sieht die offenen Namen und hört nach Browserinteraktion einen Hinweiston. Wiederholte Klicks auf dieselbe offene Bitte erzeugen keine doppelten Meldungen.

Mit **Wir fahren jetzt zur Toilettenpause ab** bestätigt der Fahrtleiter die gezeigten Anfragen. Alle Teilnehmer erhalten einen sichtbaren Hinweis, eine gespeicherte Chatnachricht und im geöffneten Browser einen Ton. Eine neue Bitte, die erst während der Bestätigung eintrifft, bleibt offen. Diese Aktion sendet keinen Fahrzeugbefehl und wählt keine Ausfahrt/Ladestation automatisch.

**Hinweistöne aktivieren** erlaubt den Browserton auf diesem Gerät; er lässt sich wieder ausschalten. Bei gesperrtem Handy wird stattdessen die erlaubte Web-Push-Zustellung verwendet. Ton, Fokusmodus und sichtbare Mitteilung hängen dort von den iOS-/Android-Einstellungen ab. Automatisierte Tests ersetzen diesen Gerätetest nicht.
