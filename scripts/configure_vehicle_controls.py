#!/usr/bin/env python3
"""Prepare TLS for the private Tesla command proxy without enabling controls."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def prepare(root):
    keys = root/'deploy/keys'
    fleet_key = keys/'tesla-private-key.pem'
    if not fleet_key.is_file():
        raise ValueError('Tesla-Schlüsselpaar fehlt. Zuerst scripts/configure.py ausführen; bestehende .env nicht ersetzen.')
    if fleet_key.stat().st_uid != os.getuid():
        raise ValueError('Dieses Skript mit demselben Benutzer ausführen, dem tesla-private-key.pem gehört. Private Schlüssel bleiben auf 0600.')
    cert, key = keys/'vehicle-command-tls.pem', keys/'vehicle-command-tls-key.pem'
    if cert.is_file() and key.is_file():
        subprocess.run(['openssl','x509','-in',str(cert),'-checkend','86400','-noout'],check=True,capture_output=True)
        return False
    if cert.exists() or key.exists():
        raise ValueError('Unvollständiges TLS-Schlüsselpaar gefunden. Vor einer bewussten Erneuerung beide Dateien sichern und entfernen.')
    # Write both files only after OpenSSL succeeds; never overwrite existing keys.
    with tempfile.TemporaryDirectory(dir=keys) as temporary:
        temporary = Path(temporary)
        subprocess.run(['openssl','req','-x509','-nodes','-newkey','ec','-pkeyopt','ec_paramgen_curve:secp384r1',
                        '-keyout',str(temporary/'key.pem'),'-out',str(temporary/'cert.pem'),'-sha256','-days','365',
                        '-subj','/CN=tesla-command-proxy','-addext','subjectAltName=DNS:tesla-command-proxy',
                        '-addext','extendedKeyUsage=serverAuth','-addext','keyUsage=digitalSignature,keyCertSign,keyAgreement'],
                       check=True,capture_output=True)
        for source,target,mode in [(temporary/'key.pem',key,0o600),(temporary/'cert.pem',cert,0o644)]:
            descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
            with os.fdopen(descriptor,'wb') as output:output.write(source.read_bytes())
            target.chmod(mode)
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:created=prepare(ROOT)
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        parser.error(str(error) if isinstance(error,ValueError) else 'TLS-Vorbereitung fehlgeschlagen oder Zertifikat läuft ab. Dateien prüfen; keine Schlüssel wurden ausgegeben.')
    print('TLS-Zertifikat erstellt.' if created else 'Vorhandenes TLS-Zertifikat ist weiterhin gültig; unverändert.')
    print('Zum Aktivieren TESLA_GROUP_CONTROLS=true in .env setzen und compose.vehicle-controls.yaml als Overlay verwenden.')
    print(f'TESLA_COMMAND_PROXY_USER={os.getuid()}:{os.getgid()} in .env eintragen. Der Proxy liest die privaten Schlüssel mit diesem Benutzer.')
    print('Jeder Fahrer benötigt vehicle_cmds, den virtuellen Fahrzeugschlüssel und eine separate Freigabe in der Fahrt.')


if __name__=='__main__':main()
