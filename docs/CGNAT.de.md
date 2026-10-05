# Sprachfunk hinter CGNAT mit VPS und WireGuard

Die Webseite und LiveKit-Signalisierung laufen über HTTPS/WebSocket. Audio läuft über eine separate WebRTC-Verbindung. Dass die Webseite funktioniert oder der Heimserver ausgehend über den VPS ins Internet kommt, beweist keine eingehende Erreichbarkeit der Audio-Ports.

| Öffentlicher Zugang am VPS | Weiterleitung über WireGuard | Ziel am Heimserver |
|---|---|---|
| 443/TCP für `teslatalk-voice.glockb.de` | bestehender HTTPS-Proxy | Traefik → LiveKit 7880 |
| 7882/UDP | direkte Portweiterleitung, gleiche Portnummer | Docker-Host 7882/UDP → LiveKit |
| 7881/TCP | direkte Portweiterleitung, gleiche Portnummer | Docker-Host 7881/TCP → LiveKit |

LiveKit muss die **öffentliche IPv4 des VPS** bekanntgeben. Eine CGNAT-Adresse oder die WireGuard-IP funktioniert dafür nicht. Mit `rtc.udp_port: 7882` benötigt diese Konfiguration keinen zusätzlichen Bereich 50000–60000. Die direkte Verbindung verschlüsselt WebRTC selbst; diese beiden Ports gehören nicht hinter einen HTTP-Router. [LiveKit-Portanforderungen](https://docs.livekit.io/transport/self-hosting/ports-firewall/)

## Bestehende Installation anpassen

In `.env` ergänzen; den Platzhalter durch die tatsächliche öffentliche VPS-IPv4 ersetzen:

```dotenv
LIVEKIT_PUBLIC_IP=DEINE_OEFFENTLICHE_VPS_IPV4
```

Dann auf dem Heimserver:

```bash
cd /mnt/docker/compose/TeslaTalk
git pull --ff-only
python3 scripts/configure_voice.py
docker compose -f compose.traefik.yaml up -d --build --force-recreate
python3 scripts/configure_voice.py --check
python3 scripts/check_cgnat.py
```

`configure_voice.py` benötigt nur Python 3 und ändert ausschließlich die RTC-IP-Einstellungen in `deploy/livekit.yaml`. Zugangsschlüssel, Ports und andere Konfiguration bleiben erhalten. Es setzt `node_ip` auf die VPS-IP und `use_external_ip: false`, weil automatische STUN-Erkennung sonst die explizite Adresse übersteuert; siehe [LiveKit-Konfiguration für Version 1.13.7](https://github.com/livekit/livekit/blob/v1.13.7/config-sample.yaml). Eine leere `LIVEKIT_PUBLIC_IP` aktiviert wieder die automatische Erkennung. Das Skript richtet keine Firewall oder Portweiterleitung ein. Wegen des erneuerten Bind-Mounts muss LiveKit **neu erstellt** werden; ein bloßer Neustart genügt nicht.

## Weiterleitung am öffentlichen Server prüfen

Falls dieses Repository auf dem VPS vorhanden ist, dort ausführen:

```bash
sudo python3 scripts/check_cgnat.py --vps
```

Alternativ direkt auf dem VPS, ohne Installation:

```bash
ip -br -4 address
sudo wg show interfaces
sudo sysctl net.ipv4.ip_forward
sudo iptables -t nat -S
sudo iptables -S FORWARD
```

Keine Ausgabe von `wg show all dump` teilen: Diese enthält private Schlüssel. Die Prüfungen oben verändern nichts. Wenn nftables statt iptables verwaltet wird, dort die NAT- und Forward-Regeln prüfen. Provider-Firewall und Heimserver-Firewall müssen die betreffenden Verbindungen ebenfalls erlauben. Breite Weiterleitungen können die Ports schon abdecken; das Fehlen einer ausdrücklich benannten 7881/7882-Regel allein beweist keinen Fehler.

Für eine gezielte Weiterleitung werden öffentliche VPS-IP, externes VPS-Interface, WireGuard-Interface sowie VPS- und Heimserver-WireGuard-IP benötigt. Bestehende Firewallregeln bleiben erhalten. Die Regeln müssen eingehend die beiden Ports per DNAT auf die Heimserver-WireGuard-IP abbilden und im Forwarding erlauben. Der Rückweg muss durch denselben Tunnel laufen; gezieltes SNAT auf die VPS-WireGuard-IP ist eine Möglichkeit, ihn sicherzustellen. Werden die Ports außen anders nummeriert, passt die von LiveKit bekanntgegebene Portnummer nicht mehr.

Cloudflare als DNS-Anbieter beziehungsweise Traefik-DNS-Challenge ersetzt diese Weiterleitung nicht. Auch ein normaler Cloudflare-HTTPS-Proxy transportiert die beiden direkten Audio-Ports nicht. Die WebSocket-Adresse kann weiterhin über den HTTPS-Proxy laufen; die Medienverbindung verwendet die von LiveKit bekanntgegebene VPS-IP. [Cloudflare-Proxy-Ports](https://developers.cloudflare.com/fundamentals/reference/network-ports/)

## Dauerhafte gezielte Weiterleitung installieren

`scripts/setup_voice_vps.py` erstellt für einen Linux-VPS mit iptables und systemd eine gezielte Weiterleitung. Ohne `--apply` druckt es ausschließlich den prüfbaren Regelblock. Mit `--apply` legt es einen eigenen Dienst und eine Einstellung für dauerhaftes IPv4-Forwarding an. Vorhandene Firewallregeln, Standardrichtlinien, UFW und Docker bleiben erhalten. Der Dienst erlaubt nur die zwei Medienports zum angegebenen WireGuard-Ziel und deren zugehörigen Rückverkehr. Die Zielports bleiben außen und innen identisch; SNAT auf die VPS-WireGuard-IP sorgt für den Rückweg durch den Tunnel.

Auf dem VPS, mit deinen tatsächlichen Adressen und Interfaces:

```bash
sudo python3 scripts/setup_voice_vps.py \
  --public-ip DEINE_OEFFENTLICHE_VPS_IPV4 \
  --home-wg-ip DEINE_HEIMSERVER_WIREGUARD_IPV4 \
  --vps-wg-ip DEINE_VPS_WIREGUARD_IPV4 \
  --wan-interface DEIN_EXTERNES_INTERFACE \
  --wg-interface wg0 \
  --apply

systemctl status teslatalk-voice-forward.service --no-pager
```

Der Dienst wird für den Systemstart aktiviert und führt die Regeln nach UFW, Docker und `wg-quick@wg0` aus, sofern diese Dienste verwendet werden. Nach einem manuellen Firewall-Reload die gezielten Regeln bei Bedarf mit `sudo systemctl reload teslatalk-voice-forward.service` wieder anwenden. Zurücknehmen: `sudo systemctl disable --now teslatalk-voice-forward.service`. Dabei entfernt der Dienst nur seine eigenen Regeln; die bereits aktivierte allgemeine IP-Weiterleitung bleibt erhalten. Provider-Firewall und Heimserver-Erreichbarkeit müssen zusätzlich geprüft werden.

## Echten Sprachtest durchführen

Zuerst eine laufende Fahrt mit zwei Geräten öffnen. „Mikrofon erlauben & Funk verbinden“ fragt die Browserfreigabe vor dem Netzwerkaufbau an. Bei schon erteilter Freigabe zeigt der Browser keinen neuen Dialog. Nach Verbindung bleibt das Mikrofon stumm, bis es per Tipp eingeschaltet wird. Der Status „DU SENDEST · MIKROFON AN“ zeigt den aktiven Sender.

Mindestens ein Gerät über Mobilfunk testen, damit der öffentliche Medienweg geprüft wird. Bleibt `could not establish pc connection`, auf dem VPS und Heimserver während des Tests den Eingang von 7882/UDP und 7881/TCP vergleichen. Eine HTTPS-Antwort 200 prüft lediglich den HTTP-Zugang. Für Clientnetze, die beide direkten Medienports sperren, kann zusätzlich TURN nötig sein; TURN ist in der Standardkonfiguration nicht aktiviert.
