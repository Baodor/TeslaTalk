#!/usr/bin/env python3
"""Register the operator's Tesla Fleet application in its configured region."""
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def main():
    root=Path(__file__).resolve().parents[1]
    values=dict(line.split('=',1) for line in (root/'.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
    client_id,secret=values.get('TESLA_CLIENT_ID'),values.get('TESLA_CLIENT_SECRET')
    app=urlsplit(values['APP_URL'])
    fleet=values.get('TESLA_FLEET_URL','https://fleet-api.prd.eu.vn.cloud.tesla.com').rstrip('/')
    if not client_id or not secret or app.scheme!='https' or fleet not in ('https://fleet-api.prd.eu.vn.cloud.tesla.com','https://fleet-api.prd.na.vn.cloud.tesla.com'):
        sys.exit('Configure an HTTPS APP_URL, Tesla client ID/secret and the official EU or NA Fleet URL first.')
    try:
        data=urlencode({'grant_type':'client_credentials','client_id':client_id,'client_secret':secret,'audience':fleet,'scope':'openid user_data vehicle_device_data vehicle_location'}).encode()
        request=Request('https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'})
        with urlopen(request,timeout=25) as response:
            token=json.load(response)['access_token']
        request=Request(fleet+'/api/1/partner_accounts',data=json.dumps({'domain':app.hostname}).encode(),
                        headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        with urlopen(request,timeout=25) as response:
            if response.status not in (200,201):
                sys.exit('Tesla did not confirm registration.')
        print('Tesla partner registration completed for '+app.hostname+'. No tokens were printed or stored.')
    except HTTPError as error:
        sys.exit('Tesla registration failed (HTTP '+str(error.code)+'). Check allowed origins, public key, permissions and region in the developer portal.')
    except (URLError,KeyError,ValueError):
        sys.exit('Tesla registration could not be completed. Check configuration and network access.')


if __name__=='__main__':
    main()
