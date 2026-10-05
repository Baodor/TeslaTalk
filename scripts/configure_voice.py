#!/usr/bin/env python3
"""Set LiveKit's advertised VPS IPv4, preserving keys and other YAML settings."""
import argparse
import ipaddress
import os
from pathlib import Path
import re
import shlex
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def public_ip(value):
    value = value.strip()
    if not value:
        return ''
    address = ipaddress.ip_address(value)
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_global or address.is_multicast:
        raise ValueError('LIVEKIT_PUBLIC_IP must be the public IPv4 of your forwarding VPS.')
    return str(address)


def env_public_ip(path):
    # Read only this non-secret value; never evaluate or source a shell file.
    value = ''
    for line in path.read_text().splitlines():
        match = re.match(r'^\s*(?:export\s+)?LIVEKIT_PUBLIC_IP\s*=\s*(.*?)\s*$', line)
        if match:
            parts = shlex.split(match[1], comments=True)
            if len(parts) > 1:
                raise ValueError('Invalid LIVEKIT_PUBLIC_IP dotenv value.')
            value = parts[0] if parts else ''
    return value


def configure(text, address):
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    starts = [index for index, line in enumerate(lines) if re.fullmatch(r'rtc:\s*(?:#.*)?\n?', line)]
    if len(starts) != 1:
        raise ValueError('Expected one top-level rtc: YAML block; adjust a custom config manually.')
    start = starts[0]
    end = next((index for index in range(start + 1, len(lines))
                if re.match(r'^[^\s#]', lines[index])), len(lines))
    fields = {'use_external_ip': 'false' if address else 'true',
              'advertise_internal_ip': 'false', 'node_ip': address or None}
    block, seen = [], set()
    for line in lines[start + 1:end]:
        match = re.match(r'^  (use_external_ip|advertise_internal_ip|node_ip):', line)
        if match:
            key = match[1]
            if key in seen:
                raise ValueError('Duplicate RTC settings; fix the YAML before continuing.')
            seen.add(key)
            if fields[key] is not None:
                block.append(f'  {key}: {fields[key]}\n')
        elif re.match(r'^\s+(use_external_ip|advertise_internal_ip|node_ip):', line):
            raise ValueError('Expected two-space RTC indentation; adjust a custom config manually.')
        else:
            block.append(line)
    for key, value in fields.items():
        if key not in seen and value is not None:
            block.append(f'  {key}: {value}\n')
    return ''.join([*lines[:start + 1], *block, *lines[end:]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-ip', help='Override LIVEKIT_PUBLIC_IP; empty means automatic STUN discovery.')
    parser.add_argument('--check', action='store_true', help='Check without changing any files.')
    args = parser.parse_args()
    path = ROOT / 'deploy/livekit.yaml'
    try:
        address = public_ip(args.public_ip if args.public_ip is not None else env_public_ip(ROOT / '.env'))
        previous = path.read_text()
        updated = configure(previous, address)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print('LiveKit advertised IPv4: ' + (address or 'automatic STUN discovery'))
    print('Media ports: 7881/TCP and 7882/UDP; forward both with the same port numbers.')
    if args.check:
        print('Configuration matches.' if updated == previous else 'Configuration needs updating: run python3 scripts/configure_voice.py')
        raise SystemExit(0 if updated == previous else 1)
    if updated != previous:
        # Atomic update. Recreate the Docker service so its bind mount sees the new inode.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix='.livekit-', delete=False) as output:
                temporary = Path(output.name)
                output.write(updated)
            temporary.chmod(0o600)
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
    print('Keys and unrelated settings are preserved. Recreate LiveKit to apply:')
    print('docker compose -f compose.traefik.yaml up -d --force-recreate livekit')


if __name__ == '__main__':
    main()
