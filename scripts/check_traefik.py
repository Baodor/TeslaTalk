#!/usr/bin/env python3
"""Show certificate resolver names and TeslaTalk TLS labels without exposing secrets."""
import json
import re
import subprocess
import sys
from urllib.parse import urlsplit


def main():
    try:
        ids = subprocess.check_output(['docker', 'ps', '-q'], stderr=subprocess.DEVNULL).decode().split()
        if not ids:
            sys.exit('No running Docker containers found.')
        containers = json.loads(subprocess.check_output(['docker', 'inspect', *ids], stderr=subprocess.DEVNULL))
    except (OSError, subprocess.CalledProcessError, ValueError):
        sys.exit('Cannot inspect Docker. Run this on the Docker host with permission to use Docker.')
    defined, used = set(), set()
    for container in containers:
        config = container.get('Config', {})
        labels = {key.lower():value for key,value in (config.get('Labels') or {}).items()}
        for argument in (config.get('Entrypoint') or []) + (config.get('Cmd') or []):
            match = re.match(r'--certificatesresolvers\.([^.]+)\.', argument, re.IGNORECASE)
            if match:
                defined.add(match[1])
        for key, value in labels.items():
            if key.startswith('traefik.http.routers.') and key.endswith('.tls.certresolver') and value:
                used.add(value)
            if key in ('traefik.http.routers.teslatalk.tls.certresolver', 'traefik.http.routers.teslatalk-voice.tls.certresolver'):
                print(key + '=' + (value or '(empty)'))
        if 'traefik.http.routers.teslatalk.rule' in labels:
            values = dict(item.split('=', 1) for item in (config.get('Env') or []) if '=' in item)
            for key, scheme in [('APP_URL', 'https'), ('LIVEKIT_URL', 'wss')]:
                try:
                    value = urlsplit(values.get(key, ''))
                    port = value.port
                except ValueError:
                    print(f'CHECK: {key} is not a valid public URL')
                    continue
                # Never print credentials, query parameters, paths or unrelated env.
                host = value.hostname or '(missing)'
                if ':' in host:
                    host = '[' + host + ']'
                if port is not None:
                    host += ':' + str(port)
                print(f'{key} origin: {value.scheme}://{host}')
                if value.scheme != scheme:
                    print(f'CHECK: production {key} must use {scheme}://')
        for router, service, port in [('teslatalk','teslatalk','8780'), ('teslatalk-voice','teslatalk-voice','7880')]:
            if f'traefik.http.routers.{router}.rule' not in labels:
                continue
            selected = labels.get(f'traefik.http.routers.{router}.service', service)
            actual = labels.get(f'traefik.http.services.{selected.lower()}.loadbalancer.server.port', '(missing)')
            print(f'{router} internal HTTP port: {actual} (expected {port})')
            network = labels.get('traefik.docker.network', 'proxy')
            connected = network in container.get('NetworkSettings', {}).get('Networks', {})
            print(f'{router} connected to Traefik network: {connected}')
    print('Resolver names defined via Traefik CLI: ' + (', '.join(sorted(defined)) or '(none; check certificatesResolvers in your Traefik configuration file)'))
    print('Resolver names referenced by Docker routers: ' + (', '.join(sorted(used)) or '(none)'))
    print('Set TRAEFIK_CERT_RESOLVER in .env to the exact name of your existing resolver.')
    print('This check does not change containers, certificates or .env. No credentials are displayed.')


if __name__ == '__main__':
    main()
