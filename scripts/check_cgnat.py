#!/usr/bin/env python3
"""Read-only media routing diagnostics. Never print WireGuard keys or Docker env."""
import argparse
import ipaddress
import json
import re
import subprocess


def command(args):
    print('$ ' + ' '.join(args))
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        print('Unavailable (tool missing, permission denied or timed out).')
        return
    if result.returncode:
        print('Unavailable (permission denied or command failed).')
        return
    print(result.stdout.strip() or '(empty)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vps', action='store_true', help='Run on the public VPS, using sudo if needed.')
    parser.add_argument('--home-wg-ip', help='On the VPS: verify the route to the home WireGuard IPv4.')
    args = parser.parse_args()
    if args.home_wg_ip:
        try:
            address = ipaddress.IPv4Address(args.home_wg_ip)
        except ValueError:
            parser.error('--home-wg-ip requires an IPv4 address.')
    command(['ip', '-br', '-4', 'address'])
    command(['ip', '-4', 'route'])
    # Deliberately avoid `wg show all dump`: it includes private and preshared keys.
    command(['wg', 'show', 'interfaces'])
    if args.vps:
        command(['sysctl', 'net.ipv4.ip_forward'])
        if args.home_wg_ip:
            command(['ip', 'route', 'get', str(address)])
        for cmd in (['iptables', '-t', 'nat', '-S'], ['iptables', '-S', 'FORWARD'], ['nft', 'list', 'ruleset']):
            # Only show forwarding/filter context for these media ports, not unrelated rules.
            print('$ ' + ' '.join(cmd) + ' (filtered to media ports)')
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode:
                    print('Unavailable; rerun with sudo if needed.')
                    continue
                matches = [line for line in result.stdout.splitlines() if re.search(r'\b788[12]\b|^-P FORWARD|chain (?:forward|prerouting|postrouting)|policy ', line, re.IGNORECASE)]
                print('\n'.join(matches) or '(no explicit 7881/7882 rules found; broad rules may also forward traffic)')
            except (OSError, subprocess.TimeoutExpired):
                print('Unavailable.')
        return
    try:
        ids = subprocess.check_output(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.service=livekit'], timeout=10).decode().split()
        for container in json.loads(subprocess.check_output(['docker', 'inspect', *ids], timeout=10)) if ids else []:
            print('LiveKit container: ' + container['Name'].lstrip('/'))
            print('Docker media bindings: ' + json.dumps({key: value for key, value in (container['NetworkSettings'].get('Ports') or {}).items() if key in ('7881/tcp', '7882/udp')}))
            for mount in container.get('Mounts', []):
                if mount.get('Destination') == '/etc/livekit.yaml':
                    from pathlib import Path
                    for line in Path(mount['Source']).read_text().splitlines():
                        if re.match(r'^  (node_ip|use_external_ip|advertise_internal_ip|tcp_port|udp_port):', line):
                            print('rtc.' + line.strip())
        if not ids:
            print('No running Compose LiveKit container found.')
    except (OSError, subprocess.SubprocessError, ValueError):
        print('Cannot inspect LiveKit; run on the Docker host with Docker permissions.')
    print('These checks do not prove end-to-end UDP reachability or change any settings.')


if __name__ == '__main__':
    main()
