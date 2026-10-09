"""Human descriptions and live schemas shared by the page and LLM export."""
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute, APIWebSocketRoute
from .config import settings

# Every API/auth handler must have an entry (enforced by coverage tests).
DETAILS = {
    'allow_vehicle_controls': ('Fahrzeugsteuerung', 'Als Fahrer Komfortsteuerung für das eigene aktuelle Fahrzeug erlauben.', 'vehicle_controls mit vehicles, configured, actions. Separate Zustimmung nur für diese aktive Fahrt und dieses Auto; unabhängig von Routenübernahme. Aktuelle Fahrer-Browsersitzung, keine Mitfahrer/API-Schlüssel. Fahrzeugwechsel hebt die Zustimmung auf. Kein Befehl durch diese Aktion.'),
    'revoke_vehicle_controls': ('Fahrzeugsteuerung', 'Eigene Komfortfreigabe sofort widerrufen.', 'vehicle_controls; verhindert nachfolgende Befehle an dieses Fahrzeug. Bereits an Tesla gesendete Befehle sind nicht zurückholbar.'),
    'send_vehicle_controls': ('Fahrzeugsteuerung', 'Als Fahrtleiter eine bestätigte Komfortaktion an freigegebene Fahrzeuge senden.', 'ControlBatch: request_id (UUID), action (frunk_open/rear_trunk_toggle/windows_vent/windows_close/climate_on/climate_off), vehicle_ids (1–100 eindeutige aktuelle IDs). Aktive Fahrer-Browsersitzung; 6 neue Aufträge/Minute, ein laufender Auftrag pro Fahrt. Gleiche UUID und gleiche Daten geben den gespeicherten Auftrag zurück, ohne Wiederholung; geänderte Daten oder Freigaben geben 409. Pro Fahrzeug status=accepted/demo/skipped/error/unknown/pending und message. Signierter TLS-Proxy, vehicle_cmds und virtueller Fahrzeugschlüssel erforderlich. Kofferraum/Fenster nur bei frischen Parkdaten; Frunk schließt manuell, Heckklappe wird betätigt. Keine Türverriegelung, kein Aufwecken oder automatisches Wiederholen.'),
    'vehicle_control_result': ('Fahrzeugsteuerung', 'Als Fahrtleiter den gespeicherten Auftragsstatus abrufen.', 'request_id, action, status=running/completed, vehicles mit Einzelergebnissen. Nur aktive Fahrer-Browsersitzung des Fahrtleiters. Diese GET-Abfrage sendet keinen Fahrzeugbefehl; 404 bei unbekanntem Auftrag.'),
    'tesla_passenger_login': ('Anmeldung', 'Tesla-Profil mit aktivem QR-Mitfahrer verknüpfen.', 'Weiterleitung mit ausschließlich openid und user_data. An die aktuelle Mitfahrer-Browsersitzung, Fahrt und einmaligen PKCE-Zustand gebunden. Kein Fahrzeugzugriff und keine gespeicherten Tesla-Tokens; Mitfahrerrolle und Sitzungsablauf bleiben bestehen.'),
    'unlink_passenger_tesla': ('Profil', 'Eigene Tesla-Profilverknüpfung als aktiver QR-Mitfahrer entfernen.', '{ok:true}; entfernt Tesla-Profilbild, Tesla-Mail und Verknüpfung. Name/PIN und Mitfahrerrolle bleiben erhalten.'),
    'admin_delete_user': ('Administration', 'Benutzer nach Eingabe seines aktuellen Benutzernamens dauerhaft löschen.', '{ok:true,deleted_user_id,deleted_trips,deleted_qr_accounts}. Löscht Konto, Fahrzeuge, Tokens, Sitzungen, Nachrichten, Messwerte und geleitete Fahrten einschließlich Gruppendaten und verwaister QR-Konten atomar. Fremde Fahrten bleiben erhalten. WebSocket-Zugänge werden geschlossen; LiveKit-Entfernung wird bis zum Ablauf bereits ausgestellter Join-Tokens wiederholt und bei Ausfällen nachgeholt.'),
    'health': ('System', 'Serverzustand prüfen.', 'Objekt mit status und version.'),
    'config': ('System', 'Öffentliche Verfügbarkeit von Demo, Tesla, OIDC, Push und Sprachfunk lesen.', 'Konfigurationsflags, APP_URL und öffentlicher VAPID-Schlüssel; keine Geheimnisse.'),
    'documentation': ('System', 'Vollständigen API-Katalog mit Regeln, Endpunkten, WebSocket und OpenAPI lesen.', 'Statischer Katalog dieser Installation; keine Kontodaten oder tatsächlichen Tokens.'),
    'openapi': ('System', 'Maschinenlesbares OpenAPI-Schema abrufen.', 'OpenAPI 3.1 mit Parametern, JSON-Schemas, Zugriffsregeln und Beschreibungen.'),
    'tesla_login': ('Anmeldung', 'Tesla OAuth mit PKCE und einmaligem, browsergebundenem state starten.', 'HTTP 307 zum Tesla-Login; setzt kurzlebiges tt_oauth-Cookie. Keine Fahrzeugbefehle.'),
    'tesla_callback': ('Anmeldung', 'Tesla-Code prüfen und Fahrer anmelden oder ein bestehendes QR-Mitfahrerprofil verknüpfen.', 'Fahrer: Token verschlüsselt speichern und HTTP 303 zur Startseite mit tt_session; neue Tesla-Fahrer wählen einen eindeutigen Benutzernamen. Profilverknüpfung: aktuelle gebundene QR-Sitzung/Fahrt erneut prüfen, nur Bild/Mail speichern, keine Tesla-Tokens oder neue Fahrer-Sitzung; HTTP 303 zur Fahrt. Fehlender Profilkontext wird abgelehnt und fällt niemals auf Fahrerlogin zurück. Bei Abbruch Weiterleitung ohne Verknüpfung.'),
    'admin_login': ('Anmeldung', 'Separaten OIDC-Login für Administratoren starten.', 'Weiterleitung zum konfigurierten OIDC-Anbieter; kurzlebiger Login-Zustand.'),
    'admin_callback': ('Anmeldung', 'OIDC-Antwort und Administratorzugehörigkeit prüfen.', 'HTTP 303 nach /admin mit separatem HttpOnly tt_admin-Cookie.'),
    'logout': ('Anmeldung', 'Aktuelle Fahrer- und Admin-Browsersitzung samt gebundener Push-Abonnements widerrufen.', '{ok:true}; entfernt Sitzungscookies. Bearer-API-Schlüssel bleiben separat widerrufbar.'),
    'demo_login': ('Anmeldung', 'Demo-Fahrer mit query anlegen/anmelden; nur bei DEMO_MODE=true.', '{ok:true} und Sitzungscookie. Zehn Logins pro Minute und IP; sonst 404/429. Keine Tesla-Verbindung.'),
    'me': ('Profil', 'Eigenes Profil lesen.', 'id, username, display_name, plate, favorite_vehicle, provider, avatar_url, needs_username (erforderliche Tesla-Ersteinrichtung), tesla_profile_linked (QR-Mitfahrerprofil; gewährt keine Fahrerrechte).'),
    'profile': ('Profil', 'Eigenen Namen, eindeutigen Benutzernamen und optionales Kennzeichen ändern; Tesla-Ersteinrichtung abschließen.', 'Aktualisiertes eigenes Profil; username 3–30 ASCII-Zeichen aus Buchstaben/Ziffern/_/-, ohne Groß-/Kleinschreibung eindeutig. 409 bei Konflikt; erfolgreiche Wahl setzt needs_username=false. display_name 1–60.'),
    'refresh_tesla_profile': ('Profil', 'Optionales Profilbild des verbundenen Tesla-Kontos neu abrufen.', 'Eigenes Profil mit HTTPS-avatar_url oder null; höchstens drei Abrufe pro Minute.'),
    'vehicles': ('Fahrzeuge', 'Eigene gespeicherte Fahrzeuge lesen.', 'Liste mit id, user_id, name, model und gecachtem data einschließlich optionaler navigation.'),
    'sync_vehicles': ('Fahrzeuge', 'Fahrzeugliste des eigenen Tesla-Kontos synchronisieren.', 'Eigene Fahrzeugliste; höchstens drei Aufrufe pro Minute. Shared-VINs erhalten kontobezogene IDs.'),
    'select_vehicle': ('Fahrzeuge', 'Eigenes Standardfahrzeug auswählen und Fahrermitgliedschaften umstellen.', '{ok:true}; Routen- und Komfortfreigaben eines anderen bisher ausgewählten Fahrzeugs werden entfernt. Mitfahrermitgliedschaften bekommen kein Fahrzeug.'),
    'refresh_vehicle': ('Fahrzeuge', 'Eigene Fahrzeugdaten ohne Aufwecken lesen und in aktive Fahrten übernehmen.', 'Normalisierte latitude/longitude, speed_kmh, heading, battery_pct, range_km, odometer_km, source, updated_at, navigation, fleet_fetched_at. Miles werden in km umgerechnet. Mindestens 60 Sekunden Cache; fünf manuelle Abrufe pro Minute gemeinsam mit Navigation.'),
    'refresh_navigation': ('Navigation', 'Navigation des eigenen Fahrzeugs ohne Aufwecken abrufen.', 'Navigation-Schema. Importierte Telemetrie bis 120 Sekunden wird bevorzugt, ansonsten vehicle_data mit 60 Sekunden Cache. Fünf manuelle Abrufe pro Minute zusammen mit Fahrzeug-/Fahrtenabruf. Kein öffentliches Teilen.'),
    'import_navigation_telemetry': ('Navigation', 'Navigationssnapshot eines eigenen Fahrzeugs aus einer Fleet-Telemetry-Integration importieren.', 'Navigation-Schema. Vollständiger Snapshot, keine partiellen Updates. RouteLine: Standard-Base64 einer ASCII-Polyline mit Genauigkeit 6, maximal 20.000 Punkte. captured_at: Unixsekunden, höchstens 120 Sekunden alt/30 Sekunden zukünftig; ältere/gleiche Telemetrie gibt 409. Beendet: active=false und Ziel/Kennzahlen/RouteLine weglassen. 30 Importe pro Minute. Freigegebene aktive Fahrten werden aktualisiert.'),
    'import_trip_navigation': ('Navigation', 'Berechnete Navigation des zuvor ausgewählten Planungsfahrzeugs aktualisieren.', 'Navigation-Schema. Fahrtleiter einer aktiven Fahrt. Vor der Auswahl eines Planungsfahrzeugs keine Gruppenroute. Die berechnete Route erscheint automatisch, nicht per manueller Freigabe.'),
    'accept_route': ('Navigation', 'Automatische Zielübernahme im eigenen Fahrzeug für diese aktive Fahrt erlauben oder nach Fehler erneut versuchen.', 'route_overview. Fahrer-Berechtigung, eigenes aktuelles Mitgliedsfahrzeug; Zustimmung bindet diese Fahrt und dieses Auto. Neue Ziele werden einmalig übernommen. Kein Aufwecken, keine anderen Fahrzeugbefehle. 3 Aktionen/Minute. Tesla plant selbst; gemeinsame Ladestopps werden nicht übertragen.'),
    'stop_following_route': ('Navigation', 'Automatische Zielübernahme im eigenen Auto widerrufen.', '{ok:true}; weitere Befehle für dieses Auto entfallen. Sichtbarkeit der Gruppenroute bleibt automatisch.'),
    'plan_route': ('Navigation', 'Planungsauto auswählen und Zieladresse zur Berechnung an diesen Tesla senden.', '{command_accepted,demo,route_overview,navigation}. Fahrtleiter und aktive Fahrt erforderlich. Andere Fahrer müssen zuvor ihre Zustimmung für das ausgewählte Auto geben. Eigenes Auto des Fahrtleiters wird bei dieser Aktion ebenfalls zur Zielübernahme angemeldet. Erst eine aktuelle Antwort/Telemetrie wird als Gruppenroute verwendet. Empfehlung separat für geringsten Akku und geringste gemeldete Reichweite; Messwerte älter als fünf Minuten ausgeschlossen.'),
    'adopt_vehicle_route': ('Navigation', 'Als Fahrtleiter die aktuelle Route eines zugestimmten Fahrerfahrzeugs als Gruppenroute übernehmen.', '{navigation,route_overview}; nur aktuelle aktive Navigation, höchstens fünf Minuten alt. Weitere zustimmende Fahrer erhalten das Ziel; der Straßenverlauf und Ladestopps werden nicht erzwungen.'),
    'report_route_problem': ('Navigation', 'Als zugestimmter Fahrer abweichende oder nicht fahrbare Route melden.', '{ok:true}; reason=different_route oder cannot_follow. Sichtbare Meldung und opt-in Push an Fahrtleiter; gleiche Meldung wird nicht wiederholt gepusht. Kein Problem ohne vorherige Zustimmung.'),
    'friends': ('Freunde', 'Eigene Freundschaften und Anfragen lesen.', 'Liste mit user, status und incoming; nur eigene Verbindungen.'),
    'request_friend': ('Freunde', 'Freundschaft per exaktem Benutzernamen, Kennzeichen oder E-Mail anfragen.', '{ok:true}; query muss einen bereits registrierten Fahrer treffen.'),
    'accept_friend': ('Freunde', 'Eingehende Freundschaftsanfrage annehmen.', '{ok:true}; nur der angefragte Fahrer kann annehmen.'),
    'delete_friend': ('Freunde', 'Eigene Freundschaft oder Anfrage entfernen.', '{ok:true}.'),
    'trips': ('Fahrten', 'Fahrten der eigenen Mitgliedschaften lesen.', 'Liste mit id, leader_id, title, destination, starts_at, ends_at, finished_at, status, participants.'),
    'create_trip': ('Fahrten', 'Fahrt mit Titel, optionalem Ziel und Zeitraum erstellen.', 'Fahrtübersicht mit sechsstelliger pin einmalig für den Fahrerbeitritt. ISO-8601-Daten brauchen Zeitzone; Zeitraum positiv, höchstens 90 Tage.'),
    'join_trip': ('Fahrten', 'Als Fahrer über die sechsstellige Fahrt-PIN beitreten.', 'Fahrtübersicht; Fahrer-PIN ist kein Mitfahrer-Login. Nur vor Fahrtende; brute-force-begrenzt.'),
    'invitations': ('Fahrten', 'An das eigene Konto gerichtete Fahrteneinladungen lesen.', 'Liste der eingeladenen Fahrten.'),
    'invite': ('Fahrten', 'Als Fahrtleiter einen existierenden Fahrer per query einladen.', '{ok:true}; query ist exakter Benutzername, Kennzeichen oder E-Mail.'),
    'accept_invite': ('Fahrten', 'Eigene Einladung vor Fahrtende annehmen.', 'Fahrtübersicht; Einladung muss dem aktuellen Fahrer gehören.'),
    'trip_detail': ('Fahrten', 'Berechtigte Fahrt mit Mitgliedern, Fahrzeugdaten und berechneter Gruppenroute lesen.', 'Fahrtübersicht plus participants_detail, my_role, navigation (oder null), vehicle_controls (Fahrerübersicht; für Mitfahrer null), route_overview (Fahrzeugliste mit Akku/Reichweite, Zustimmung, Problemen und getrennten Empfehlungen), album (status:planned, url:null). Vor erster Planungsfahrzeugauswahl bleibt navigation=null. Keine Immich-Verbindung.'),
    'add_passenger': ('Mitfahrer', 'Als Fahrtleiter einen namentlichen Mitfahrer anlegen.', 'Mitfahrer-ID, Name und individuelle sechsstellige PIN einmalig. Kein Tesla-Konto notwendig.'),
    'guest_info': ('Mitfahrer', 'Öffentliche Minimalinformationen zu einem Mitfahrerlink lesen.', 'Titel, Start/Ende und aktuelles Zugangsfenster; keine Teilnehmer oder GPS-Daten.'),
    'guest_register': ('Mitfahrer', 'Über den QR-Link selbst mit Name und gewähltem sechsstelligen PIN registrieren und der aktiven Fahrt beitreten.', 'trip_id und begrenzte Sitzung; Name pro Fahrt ohne Groß-/Kleinschreibung eindeutig. 409 bei vorhandenem Namen, 403 außerhalb des Fahrtzeitraums. 20 Versuche pro fünf Minuten und IP/Link. Keine Fahrerrechte, PIN wird nicht zurückgegeben.'),
    'guest_login': ('Mitfahrer', 'Namentlichen Mitfahrer mit seiner PIN im Fahrtzeitraum anmelden.', 'Sitzung und trip_id; PIN und Name müssen zusammengehören. Ablauf spätestens zum Fahrtende. Fünf Versuche pro fünf Minuten und IP/Link/Name; zusätzlich 60 pro IP/Link. Gemeinsame IP erlaubt mehrere unterschiedliche Mitfahrer.'),
    'messages': ('Chat', 'Private Chatnachrichten der Fahrt lesen.', 'Neueste 100 Nachrichten chronologisch; before ist Unix-Zeitstempel zur Abfrage älterer Nachrichten.'),
    'post_message': ('Chat', 'Nichtleere Nachricht vor Fahrtende senden.', 'Gespeicherte Nachricht mit id, trip_id, user_id, display_name, text und created_at; WebSocket-Event und Push an optierte andere Teilnehmer.'),
    'upload_sample': ('Standort & Messwerte', 'Persönlichen Browserstandort oder Fahrzeugtelemetrie in aktiver Fahrt speichern.', '{ok:true}. source=browser: Fahrer/Mitfahrer, Koordinatenpaar erforderlich, nur persönlicher Standort/Tempo/Richtung; keine Fahrzeugwerte. source=telemetry: Fahrer-Bearer erforderlich. 15 Aufrufe/Minute. Energie/Kilometerzähler sind kumulative Messwerte, keine Schätzungen.'),
    'stop_location': ('Standort & Messwerte', 'Eigene Live-Standortfreigabe einer Fahrt beenden.', '{ok:true}; entfernt nur Personenmarker. Fahrzeugposition und aufgezeichnete Historie bleiben.'),
    'history': ('Standort & Messwerte', 'Berechtigte Messwerthistorie paginiert lesen.', 'Liste in ID-Reihenfolge: after_id exklusiv, limit standardmäßig 1.000, begrenzt auf 1–5.000.'),
    'export_history': ('Standort & Messwerte', 'Alle privaten Fahrtmesswerte als JSON-Datei exportieren.', 'Streaming-JSON-Liste mit Content-Disposition; kein Seitenlimit.'),
    'trip_ranking': ('Standort & Messwerte', 'Kennzahlen aus gemessenen Fahrzeugzählern lesen.', 'Liste je Fahrer mit distance_km, duration_seconds, average_speed_kmh, consumption_kwh_100km. Fehlende/resetete Zähler ergeben null; Verbrauch erst ab mindestens 1 km. Browserstandorte und Mitfahrer ausgeschlossen.'),
    'voice_access': ('Sprachfunk', 'Mikrofon-only LiveKit-Token für die eigene aktive Fahrt beziehen.', '{token,url,ends_at}; Raum-/Fahrtbindung, keine Kamerapublikation. Ablauf spätestens zum Fahrtende. 503 bei fehlendem/unverfügbarem LiveKit.'),
    'finish_trip': ('Fahrten', 'Als Fahrtleiter die Fahrt jetzt beenden.', '{ok:true}; schließt Mitfahrerzugänge, entfernt Live-Personenmarker, beendet Sprachraum und sendet ended.'),
    'share_trip': ('Freigaben', 'Als Fahrtleiter nach Fahrtende öffentlichen Leselink erzeugen/ersetzen.', '{url}; neuer Schlüssel ersetzt den alten. Öffentlich keine Identitäten, Kennzeichen, Chats, Navigation oder GPS-Historie.'),
    'revoke_share': ('Freigaben', 'Öffentlichen Leselink der eigenen geleiteten Fahrt widerrufen.', '{ok:true}; bisheriger Link liefert danach 404.'),
    'public_trip': ('Freigaben', 'Öffentliche, rein lesende Fahrtübersicht lesen.', 'title, destination, starts_at, ends_at, album (planned), read_only:true; keine private Navigation.'),
    'keys': ('API-Schlüssel', 'Metadaten eigener persönlicher API-Schlüssel lesen.', 'Liste mit id, label, expires_at (Unixsekunden oder null), created_at. Tokens werden nie erneut ausgegeben.'),
    'create_key': ('API-Schlüssel', 'Persönlichen API-Schlüssel erzeugen.', '{id,token,expires_at}; Token nur einmal hier ausgegeben. days 1–365, Standard 30; null bedeutet ohne Ablaufdatum. Fünf Erstellungen/Minute. Schlüssel bekommen nur Fahrerrechte, niemals Adminrechte.'),
    'delete_key': ('API-Schlüssel', 'Eigenen API-Schlüssel sofort widerrufen.', '{ok:true}; Bearer-Zugriffe damit scheitern anschließend mit 401.'),
    'push_subscribe': ('Benachrichtigungen', 'Eigenes Browser-Web-Push-Abonnement opt-in registrieren/erneuern.', '{ok:true,expires_at}; endpoint und keys.p256dh/keys.auth erforderlich; optional language=de/en/nl pro Gerät. An aktuelle Browsersitzung gebunden; Gäste nur während ihrer aktiven Fahrt.'),
    'push_unsubscribe': ('Benachrichtigungen', 'Eigenes Web-Push-Abonnement per endpoint entfernen.', '{ok:true}.'),
    'push_test': ('Benachrichtigungen', 'Aktuelles Browsergerät direkt testen und optional Abonnement zugleich neu binden.', '{ok:true,accepted_by_provider:true,provider_accepted_at,provider_elapsed_ms}; drei Tests/Minute. Optional keys aus PushSubscription.toJSON() und language=de/en/nl; ohne keys bereits registriertes, sitzungsgebundenes endpoint erforderlich. 410 bei abgelaufenem Gerät. Providerannahme garantiert keine Anzeige auf dem Handy.'),
    'admin': ('Administration', 'Instanzübersicht über separate Admin-Sitzung lesen.', 'version, users, trips, samples, online, tesla_ready, voice_ready, poll_interval, demo, push_ready, storage. Keine Kontogeheimnisse.'),
    'admin_users': ('Administration', 'Alle Benutzer mit Kontaktdaten und zuletzt erfasstem Login auflisten.', 'Liste: id, provider, display_name, username, email, plate, avatar_url, created_at, last_login_at. Unbekannte ältere Loginzeiten und fehlende Mail/Bild sind null. Keine Tokens, PIN-Hashes oder Fahrzeugstandorte.'),
    'admin_push_test': ('Administration', 'Test für alle aktiven, optierten Geräte in persistente Outbox einreihen.', '{ok:true,queued_accounts,queued_devices}; drei Broadcasts/Minute; keine garantierte Gerätezustellung.'),
    'trip_socket': ('WebSocket', 'Autorisierte Präsenz und Fahrtupdates empfangen.', 'Serverevents: participants (Teilnehmerliste), message (Nachricht), navigation (Snapshot oder null), controls (Komfortfreigaben), heartbeat, ended. Kein Audio. Berechtigung bei Verbindung, regelmäßig und vor Broadcasts geprüft. Schließen: 1008 unerlaubt/abgelaufen, 1009 bei Clientnachrichten über 1.024 Zeichen.'),
    'tesla_public_key': ('Tesla-Registrierung', 'Öffentlichen Tesla-Fahrzeugschlüssel für die Domain lesen.', 'PEM-Datei; 404 ohne eingerichteten öffentlichen Schlüssel. Kein privater Schlüssel.'),
}
PUBLIC = {'health','config','tesla_login','tesla_callback','admin_login','admin_callback','logout','demo_login','guest_info','guest_register','guest_login','public_trip','tesla_public_key'}
DRIVERS = {'profile','refresh_tesla_profile','vehicles','sync_vehicles','select_vehicle','refresh_vehicle','refresh_navigation','import_navigation_telemetry','friends','request_friend','accept_friend','delete_friend','create_trip','join_trip','invite','accept_invite','add_passenger','keys','create_key','delete_key','import_trip_navigation','accept_route','stop_following_route','plan_route','adopt_vehicle_route','report_route_problem'}
LEADERS = {'invite','add_passenger','finish_trip','share_trip','revoke_share','import_trip_navigation','plan_route','adopt_vehicle_route'}


def documented_routes(app):
    return [r for r in app.routes if isinstance(r,(APIRoute,APIWebSocketRoute)) and
            (r.path.startswith(('/api/','/auth/')) or r.path == '/.well-known/appspecific/com.tesla.3p.public-key.pem')]


def access_info(name):
    if name in PUBLIC:
        return 'public', 'Ohne Anmeldung; Login-Callbacks prüfen zusätzlich einmaligen Browserzustand.' if name.endswith('callback') else 'Ohne Anmeldung.'
    if name in {'admin','admin_users','admin_push_test','admin_delete_user'}:
        return 'admin', 'Separate OIDC-Admin-Browsersitzung (tt_admin); Fahrer-Bearer genügt nicht.'
    if name in {'allow_vehicle_controls','revoke_vehicle_controls','send_vehicle_controls','vehicle_control_result'}:
        return 'browser', 'Aktuelle Fahrer-Browsersitzung (tt_session), aktive Fahrt und eigenes Mitgliedsfahrzeug; kein API-Schlüssel. Gruppenbefehle und Auftragsstatus zusätzlich nur Fahrtleiter.'
    if name in {'push_subscribe','push_test','tesla_passenger_login','unlink_passenger_tesla'}:
        return 'browser', 'Aktuelle Fahrer-/Mitfahrer-Browsersitzung (tt_session); kein API-Schlüssel. Gäste nur während ihrer Fahrt.'
    if name == 'import_navigation_telemetry':
        return 'bearer', 'Persönlicher Fahrer-Bearer; nur eigenes Fahrzeug.'
    scope = 'Fahrer; keine Mitfahrer.' if name in DRIVERS else 'Fahrer oder gültiger Mitfahrer.'
    if name in LEADERS:
        scope += ' Nur Fahrtleiter der betreffenden Fahrt.'
    return 'user', 'tt_session oder persönlicher Bearer. '+scope


def enriched_openapi(app):
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(title=app.title,version=app.version,routes=[r for r in documented_routes(app) if isinstance(r,APIRoute)])
    schema['servers'] = [{'url':'/','description':'Gleicher Ursprung wie TeslaTalk'}]
    schema.setdefault('components',{})['securitySchemes'] = {
        'UserSession': {'type':'apiKey','in':'cookie','name':'tt_session'},
        'PersonalApiKey': {'type':'http','scheme':'bearer','description':'Persönlicher TeslaTalk-API-Schlüssel, niemals Tesla-Access-Token.'},
        'AdminSession': {'type':'apiKey','in':'cookie','name':'tt_admin'},
    }
    for route in documented_routes(app):
        if not isinstance(route,APIRoute):
            continue
        name = route.endpoint.__name__
        group, description, returns = DETAILS.get(name,('Weitere Endpunkte',getattr(route,'summary',None) or name,'Siehe Schema.'))
        auth, access = access_info(name)
        for method in route.methods:
            operation = schema['paths'][route.path][method.lower()]
            operation.update(summary=description,description=description+'\n\nZugriff: '+access+'\n\nAntwort/Verhalten: '+returns,tags=[group])
            operation['security'] = {'public':[], 'admin':[{'AdminSession':[]}], 'browser':[{'UserSession':[]}], 'bearer':[{'PersonalApiKey':[]}], 'user':[{'UserSession':[]},{'PersonalApiKey':[]}]}[auth]
            if name in {'tesla_login','tesla_passenger_login','tesla_callback','admin_login','admin_callback'}:
                operation['responses'].pop('200',None)
                status = '303' if name.endswith('callback') else '302' if name == 'admin_login' else '307'
                operation['responses'][status] = {'description':returns}
                if name == 'tesla_callback':
                    operation['responses']['307'] = {'description':'Tesla-Anmeldung abgebrochen; Weiterleitung zur Startseite.'}
            else:
                operation['responses'].setdefault('200',{})['description'] = returns
    app.openapi_schema = schema
    return schema


def catalog(app):
    schema = enriched_openapi(app)
    endpoints = []
    for route in documented_routes(app):
        name = route.endpoint.__name__
        group, description, returns = DETAILS.get(name,('Weitere Endpunkte',getattr(route,'summary',None) or name,'Siehe Schema.'))
        auth, access = access_info(name)
        methods = ['WEBSOCKET'] if isinstance(route,APIWebSocketRoute) else sorted(route.methods)
        for method in methods:
            operation = schema['paths'].get(route.path,{}).get(method.lower(),{})
            endpoints.append({'method':method,'path':route.path,'group':group,'description':description,
                              'authentication':auth,'access':access,'returns':returns,
                              'parameters':operation.get('parameters',[{'name':'trip_id','in':'path','required':True,'schema':{'type':'string'}}] if method == 'WEBSOCKET' else []),'request_body':operation.get('requestBody'),
                              'responses':operation.get('responses',{}),'operation_id':operation.get('operationId')})
    return {
        'title':'TeslaTalk API','version':app.version,'base_url':settings.app_url,'documentation_url':settings.app_url+'/api-docs',
        'rules':[
            'Tesla-Erstanmeldung: GET /api/me meldet needs_username=true. Vor Fahreraktionen einen eindeutigen Benutzernamen mit PATCH /api/me wählen: 3–30 Zeichen, Buchstaben/Ziffern/_/-, ohne Groß-/Kleinschreibung eindeutig. Konflikte ergeben 409; Profiländerungen sind für die Ersteinrichtung zugelassen.',
            'Mitfahrer registrieren sich während der aktiven Fahrt über POST /api/guest/{key}/register mit name und selbst gewähltem sechsstelligen pin. Danach reicht /login mit Name/PIN. Bestehende Namen werden nicht überschrieben; Mitfahrer erhalten keine Fahrzeugsteuerung. Die Sitzung endet mit der Fahrt. PINs und Login-Zeitpunkte werden nicht öffentlich gelistet.',
            'HTTP-Pfade relativ zu base_url. Zeitstempel in Unixsekunden; Fahrten-Eingabedaten als ISO 8601 mit Zeitzone. Kilometer, km/h und Prozent sind normalisiert.',
            'Browser: HttpOnly tt_session, credentials same-origin. Schreibende Cookie-Anfragen benötigen Origin gleich APP_URL. Integration: Authorization: Bearer <PERSONAL_API_KEY>. Ungültiger Bearer fällt niemals auf Cookies zurück.',
            'Adminrechte nur über separaten OIDC-Login und tt_admin. Persönliche Schlüssel bekommen niemals Adminrechte. Fahrtrechte und Zeitgrenzen gelten auch für unbegrenzt gültige Schlüssel.',
            'Trip-Endpunkte erfordern eigene Mitgliedschaft. Fremde Fahrten/Fahrzeuge geben 404. Gäste verlieren Zugriff am Fahrtende. Aktive Aktionen prüfen Start, Ende und Mitgliedschaft.',
            'Fehler üblicherweise {detail:string}; Validierung {detail:[...]}. 400 ungültige Anfrage/Loginzustand, 401 Anmeldung/Schlüssel ungültig, 403 Rechte/Ursprung/Zeitraum, 404 nicht gefunden/kein Zugriff, 409 Konflikt/fehlende Verbindung/Daten, 410 Push-Gerät abgelaufen, 413 Body über 1 MiB, 422 Validierung, 429 Anfragelimit, 502 externer Tesla-/Push-Fehler, 503 Dienst nicht bereit. Allgemeine mögliche Codes, kein Versprechen jedes Endpunkts.',
            'Fahrzeugabfragen wecken keine Autos. Fleet vehicle_data liefert Ziel/Reststrecke/ETA; genauer Straßenverlauf nur über importierte Fleet Telemetry RouteLine (Base64 + Polyline6). Kein eingebauter Tesla-Telemetrieempfänger. Navigation_request sendet nur Zieladressen; TESLA_NAVIGATION_COMMANDS=true und erneuter Tesla-Login mit vehicle_cmds sind für reale Zielbefehle erforderlich. Ein konfigurierter HTTPS-Command-Proxy wird mit Zertifikatprüfung und optionaler CA genutzt, ohne direkten Fleet-API-Wiederholungsversuch bei Fehlern. Teslas Proxy leitet navigation_request selbst über REST weiter.',
            'Komfortsteuerung braucht eine separate Zustimmung pro aktiver Fahrt und aktuellem eigenen Fahrerfahrzeug. Nur der Fahrtleiter sendet die sechs definierten Aktionen per Browsersitzung; kein Bearer und keine Mitfahrer. TLS-verified signierter Command-Proxy, vehicle_cmds und virtueller Schlüssel nötig. UUID verhindert erneute Ausführung desselben Auftrags, GET-Auftragsstatus ist rein lesend; nach unklarem Ergebnis tatsächlichen Zustand am Auto prüfen. Keine Türverriegelung/Entriegelung.',
            'QR-Mitfahrer dürfen Tesla ausschließlich für Profilbild und Mail verknüpfen: GET /auth/tesla/passenger?trip_id=<TRIP_ID> mit eigener aktiver QR-Browsersitzung. openid/user_data, keine gespeicherten Tesla-Tokens oder Fahrzeugrechte; QR-Name/PIN und Zugangsende bleiben erhalten. DELETE /api/me/tesla-profile-link entfernt die Verknüpfung.',
            'Benutzerlöschung nur über separate Admin-Sitzung und exakten aktuellen Benutzernamen im Body. Löscht dauerhaft Konto, Zugänge, eigene Daten und geleitete Fahrten samt Gruppendaten und verwaisten QR-Konten. Fremde Fahrten bleiben bestehen. Kein Löschversuch durch Kopieren des API-Katalogs.',
            'Zuerst wählt der Fahrtleiter anhand Akku/Reichweite ein Planungsauto. Dessen berechnete Route erscheint automatisch für die Gruppe. Weitere Fahrer müssen Zielübernahme im eigenen Auto erlauben. Straßenverlauf/Ladestopps werden damit nicht identisch übernommen; charging_stops_confirmed=false. Ohne vollständige Linien bleibt der Vergleich unconfirmed, mit Linien wird eine geometrische Toleranz von 200 m verwendet. Öffentliche Leselinks enthalten keine Navigation.',
            'WebSocket: wss bei HTTPS, ws lokal. Browser senden tt_session und Origin; externe Clients können Bearer-Header setzen. Ohne Origin ist Bearer erforderlich. Events sind Serverupdates; Chat und Messwerte werden über HTTP gesendet.',
            'Personenstandorte und Fahrzeugdaten getrennt; Live-Browserstandorte verfallen nach fünf Minuten. Historie bleibt intern. Verbrauch braucht echte kumulative Energie-/Kilometerzähler.',
            'Immich und Foto-Uploads noch nicht implementiert. album.status=planned und album.url=null bedeuten keine Fotobibliothekanbindung.',
            'Export nur mit statischen Informationen und Schemas. Keine tatsächlichen Tokens, Cookies, PINs, VINs oder Kontodaten. Platzhalter bewusst ersetzen; keine Endpunkte automatisch ausführen.',
        ],
        'examples':{
            'guest_registration':{'name':'Mein Name','pin':'<CHOSEN_SIX_DIGIT_PIN>'},
            'bearer_request':'curl -H "Authorization: Bearer <PERSONAL_API_KEY>" "'+settings.app_url+'/api/me"',
            'create_trip':{'title':'Gemeinsame Fahrt','destination':'Darmstadt','starts_at':'2026-10-10T09:00:00+02:00','ends_at':'2026-10-10T18:00:00+02:00'},
            'create_key_without_expiration':{'label':'Meine Integration','days':None},
            'vehicle_sample':{'source':'telemetry','latitude':49.8728,'longitude':8.6512,'speed_kmh':75,'battery_pct':78,'odometer_km':12050.5,'energy_used_kwh':1987.2},
            'navigation_telemetry':{'active':True,'destination':'Darmstadt Hauptbahnhof','destination_latitude':49.8728,'destination_longitude':8.6289,'distance_remaining_km':2.1,'minutes_remaining':6,'battery_arrival_pct':76,'traffic_delay_minutes':0,'captured_at':'<CURRENT_UNIX_SECONDS>','route_line':'<OPTIONAL_TESLA_BASE64_POLYLINE6>'},
            'navigation_cancelled':{'active':False,'captured_at':'<CURRENT_UNIX_SECONDS>'},
        },
        'endpoints':sorted(endpoints,key=lambda e:(e['group'],e['path'],e['method'])),
        'openapi':schema,
    }
