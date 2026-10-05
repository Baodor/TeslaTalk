#!/usr/bin/env python3
"""Generate local configuration and EC keys without printing any secrets."""
import argparse
import base64
import os
from pathlib import Path
import secrets
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def openssl(*args):
    return subprocess.run(['openssl', *map(str, args)], check=True, capture_output=True).stdout


def encoded(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:8780')
    parser.add_argument('--voice-url', default='ws://localhost:7880')
    parser.add_argument('--email', default='admin@example.com')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()
    env_path = ROOT/'.env'
    if env_path.exists():
        parser.error('.env exists. Edit it directly; this script will not replace encryption keys or existing settings.')
    app, voice = urlsplit(args.url), urlsplit(args.voice_url)
    if app.scheme not in ('http','https') or voice.scheme not in ('ws','wss') or not app.hostname or not voice.hostname or app.path not in ('','/') or voice.path not in ('','/') or any((app.username,voice.username,app.query,voice.query,app.fragment,voice.fragment)):
        parser.error('Use complete origins without paths, credentials, query strings or fragments.')
    if app.scheme=='https' and voice.scheme!='wss':
        parser.error('An HTTPS application requires a wss:// voice URL.')
    if any(character in args.email for character in '\r\n') or '@' not in args.email:
        parser.error('Enter a valid administrator email address for VAPID.')
    os.umask(0o077)
    keys = ROOT/'deploy/keys'
    keys.mkdir(parents=True,exist_ok=True)
    vapid_path = keys/'vapid-private.pem'
    if not vapid_path.exists():
        openssl('ecparam','-name','prime256v1','-genkey','-noout','-out',vapid_path)
    private = encoded(openssl('ec','-in',vapid_path,'-outform','DER'))
    public = encoded(openssl('ec','-in',vapid_path,'-pubout','-outform','DER')[-65:])
    tesla_private = keys/'tesla-private-key.pem'
    if not tesla_private.exists():
        openssl('ecparam','-name','prime256v1','-genkey','-noout','-out',tesla_private)
    openssl('ec','-in',tesla_private,'-pubout','-out',keys/'tesla-public-key.pem')
    # Only the public Tesla key is mounted inside the app container.
    (keys/'tesla-public-key.pem').chmod(0o644)
    livekit_key, livekit_secret = 'tt_'+secrets.token_hex(12), secrets.token_urlsafe(48)
    values = {
        'APP_URL':args.url.rstrip('/'),'APP_HOST':app.hostname,'APP_TIMEZONE':'Europe/Berlin','TRAEFIK_CERT_RESOLVER':'',
        'APP_SECRET':secrets.token_urlsafe(48),'DEMO_MODE':str(args.demo).lower(),
        'TESLA_CLIENT_ID':'','TESLA_CLIENT_SECRET':'','TESLA_FLEET_URL':'https://fleet-api.prd.eu.vn.cloud.tesla.com',
        'LIVEKIT_URL':args.voice_url.rstrip('/'),'VOICE_HOST':voice.hostname,
        'LIVEKIT_API_KEY':livekit_key,'LIVEKIT_API_SECRET':livekit_secret,'LIVEKIT_PUBLIC_IP':'','FLEET_POLL_INTERVAL':'120',
        'VAPID_PRIVATE_KEY':private,'VAPID_PUBLIC_KEY':public,'VAPID_SUBJECT':'mailto:'+args.email,
        'OIDC_ISSUER':'','OIDC_CLIENT_ID':'','OIDC_CLIENT_SECRET':'','OIDC_TOKEN_AUTH_METHOD':'client_secret_basic','OIDC_SCOPES':'openid email profile',
        'OIDC_GROUPS_CLAIM':'groups','ADMIN_GROUP':'teslatalk-admin','ADMIN_EMAILS':'',
    }
    env_path.write_text('# Generated locally. Keep this file private and back it up.\n'+'\n'.join(f'{key}={value}' for key,value in values.items())+'\n')
    env_path.chmod(0o600)
    (ROOT/'deploy/livekit.yaml').write_text(f'''port: 7880
rtc:
  tcp_port: 7881
  udp_port: 7882
  use_external_ip: true
keys:
  {livekit_key}: {livekit_secret}
room:
  auto_create: false
  empty_timeout: 60
logging:
  level: warn
''')
    (ROOT/'deploy/livekit.yaml').chmod(0o600)
    print('Created .env, deploy/livekit.yaml and local EC keys. No secrets were printed.')
    print('Next: docker compose up -d --build (local), or follow docs/SETUP.md for HTTPS/Traefik.')


if __name__=='__main__':
    main()
