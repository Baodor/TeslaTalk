#!/usr/bin/env python3
"""Register the operator's Tesla Fleet application in its configured region."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
KEY_PATH = '/.well-known/appspecific/com.tesla.3p.public-key.pem'
REGIONS = ('https://fleet-api.prd.eu.vn.cloud.tesla.com', 'https://fleet-api.prd.na.vn.cloud.tesla.com')


def read_env(path):
    """Read literal dotenv values, including quotes, without executing shell code."""
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.removeprefix('export ').split('=', 1)
        value = value.strip()
        if value.startswith(('"', "'")):
            parts = shlex.split(value, comments=True)
            if len(parts) != 1:
                raise ValueError('Invalid quoted setting')
            value = parts[0]
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        values[key.strip()] = value
    return values


def public_der(pem):
    result = subprocess.run(['openssl', 'pkey', '-pubin', '-outform', 'DER'], input=pem,
                            capture_output=True, check=True).stdout
    # SubjectPublicKeyInfo for an uncompressed secp256r1 EC public key.
    prefix = bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d03010703420004')
    if len(result) != 91 or not result.startswith(prefix):
        raise ValueError('The Tesla public key must use prime256v1 / secp256r1')
    return result


def check_public_key(origin):
    with urlopen(origin + KEY_PATH, timeout=25) as response:
        pem = response.read(4097)
    if len(pem) > 4096 or not pem.startswith(b'-----BEGIN PUBLIC KEY-----'):
        raise ValueError('The public key URL does not serve a PEM public key')
    if public_der(pem) != public_der((ROOT/'deploy/keys/tesla-public-key.pem').read_bytes()):
        raise ValueError('The hosted public key differs from deploy/keys/tesla-public-key.pem')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check configuration and hosted public key without registering with Tesla')
    args = parser.parse_args(argv)
    try:
        values = read_env(ROOT/'.env')
    except (OSError, ValueError):
        sys.exit('Cannot read .env. Check that it exists and quoted settings are valid.')
    client_id,secret=values.get('TESLA_CLIENT_ID'),values.get('TESLA_CLIENT_SECRET')
    app=urlsplit(values.get('APP_URL', ''))
    fleet=values.get('TESLA_FLEET_URL','https://fleet-api.prd.eu.vn.cloud.tesla.com').rstrip('/')
    if not client_id or not secret or app.scheme!='https' or not app.hostname or app.path not in ('', '/') or any((app.username, app.password, app.query, app.fragment)) or fleet not in REGIONS:
        sys.exit('Configure an HTTPS APP_URL, Tesla client ID/secret and the official EU or NA Fleet URL first.')
    phase = 'public-key check'
    try:
        check_public_key(values['APP_URL'].rstrip('/'))
        print('Public key is reachable, uses secp256r1 and matches the local public key.')
        print('Allowed origin: '+values['APP_URL'].rstrip('/'))
        print('Redirect URI: '+values['APP_URL'].rstrip('/')+'/auth/tesla/callback')
        print('Fleet region: '+fleet)
        if args.check:
            print('Preflight passed. No registration request was sent; credentials must still be accepted by Tesla.')
            return
        phase = 'partner-token request'
        data=urlencode({'grant_type':'client_credentials','client_id':client_id,'client_secret':secret,'audience':fleet,'scope':'openid user_data vehicle_device_data vehicle_location'}).encode()
        request=Request('https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'})
        with urlopen(request,timeout=25) as response:
            token=json.load(response)['access_token']
        if not isinstance(token, str) or not token:
            raise ValueError('Missing partner token')
        phase = 'partner registration'
        request=Request(fleet+'/api/1/partner_accounts',data=json.dumps({'domain':app.hostname}).encode(),
                        headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        with urlopen(request,timeout=25) as response:
            if response.status not in (200,201):
                sys.exit('Tesla did not confirm registration.')
        print('Tesla partner registration completed for '+app.hostname+'. No tokens were printed or stored.')
    except HTTPError as error:
        hints = {400:'Check allowed origins, domain, scopes and region.',
                 401:'Check Tesla client ID and secret.',
                 403:'Check application approval, allowed origins and permissions.',
                 404:'Check the public key URL and Fleet region.'}
        sys.exit(phase+' failed (HTTP '+str(error.code)+'). '+hints.get(error.code, 'Check the developer portal and retry later.'))
    except ValueError:
        # Never print Tesla response bodies or credential values.
        sys.exit('Tesla setup failed during '+phase+'. Check .env, the hosted EC public key and the local public key.')
    except (URLError,KeyError,OSError,subprocess.CalledProcessError):
        sys.exit('Tesla registration could not be completed. Check configuration and network access.')


if __name__=='__main__':
    main()
