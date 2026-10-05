#!/usr/bin/env python3
"""Prepare or install persistent, port-specific LiveKit forwarding on a WireGuard VPS."""
import argparse
import ipaddress
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess


def ipv4(value, public=False):
    address = ipaddress.IPv4Address(value)
    if address.is_unspecified or address.is_loopback or address.is_multicast or public and not address.is_global:
        raise ValueError('Use a valid public VPS IPv4 and valid WireGuard IPv4 addresses.')
    return str(address)


def interface(value):
    if not re.fullmatch(r'[A-Za-z0-9_.:+-]{1,15}', value):
        raise ValueError('Invalid interface name.')
    return value


def rules(public, home, vps, wan, wg):
    result = []
    for protocol, port in [('tcp', '7881'), ('udp', '7882')]:
        result.extend([
            ['nat', 'PREROUTING', '-i', wan, '-d', public, '-p', protocol, '--dport', port, '-j', 'DNAT', '--to-destination', home + ':' + port],
            ['nat', 'POSTROUTING', '-o', wg, '-d', home, '-p', protocol, '--dport', port, '-j', 'SNAT', '--to-source', vps],
            ['filter', 'FORWARD', '-i', wan, '-o', wg, '-d', home, '-p', protocol, '--dport', port, '-m', 'conntrack', '--ctstate', 'NEW,ESTABLISHED', '-j', 'ACCEPT'],
            ['filter', 'FORWARD', '-i', wg, '-o', wan, '-s', home, '-p', protocol, '--sport', port, '-m', 'conntrack', '--ctstate', 'ESTABLISHED', '-j', 'ACCEPT'],
        ])
    return result


def render(rule_list, iptables):
    lines = ['#!/bin/bash', '# Managed by TeslaTalk setup_voice_vps.py.', 'set -euo pipefail',
             'action="${1:-apply}"', 'case "$action" in apply|remove) ;; *) exit 2 ;; esac']
    for table, chain, *args in rule_list:
        # A comment makes the precise rules identifiable without changing other chains.
        args = ['-m', 'comment', '--comment', 'teslatalk-voice', *args]
        check = shlex.join([iptables, '-w', '10', '-t', table, '-C', chain, *args])
        add = shlex.join([iptables, '-w', '10', '-t', table, '-I', chain, '1', *args])
        delete = shlex.join([iptables, '-w', '10', '-t', table, '-D', chain, *args])
        lines.extend(['if [[ "$action" == apply ]]; then', f'  if ! {check} 2>/dev/null; then {add}; fi',
                      'else', f'  while {check} 2>/dev/null; do {delete}; done', 'fi'])
    return '\n'.join(lines) + '\n'


UNIT = '''# Managed by TeslaTalk setup_voice_vps.py.
[Unit]
Description=TeslaTalk LiveKit media forwarding through WireGuard
Wants=network-online.target
After=network-online.target ufw.service docker.service wg-quick@wg0.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/teslatalk-voice-forward apply
ExecReload=/usr/local/sbin/teslatalk-voice-forward apply
ExecStop=/usr/local/sbin/teslatalk-voice-forward remove

[Install]
WantedBy=multi-user.target
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-ip', required=True)
    parser.add_argument('--home-wg-ip', required=True)
    parser.add_argument('--vps-wg-ip', required=True)
    parser.add_argument('--wan-interface', required=True)
    parser.add_argument('--wg-interface', default='wg0')
    parser.add_argument('--apply', action='store_true', help='Install and activate; otherwise print a reviewable script only.')
    args = parser.parse_args()
    try:
        public, home, vps = ipv4(args.public_ip, public=True), ipv4(args.home_wg_ip), ipv4(args.vps_wg_ip)
        wan, wg = interface(args.wan_interface), interface(args.wg_interface)
        if home == vps or wan == wg:
            raise ValueError('VPS/home addresses and WAN/WireGuard interfaces must differ.')
    except ValueError as error:
        parser.error(str(error))
    program = render(rules(public, home, vps, wan, wg), shutil.which('iptables') or '/usr/sbin/iptables')
    if not args.apply:
        print(program, end='')
        print('# Review only. No rules or files changed. Add --apply to install the service.')
        return
    if os.geteuid() != 0 or not shutil.which('iptables') or not shutil.which('systemctl'):
        parser.error('Run with sudo on the VPS, with iptables and systemd installed.')
    if Path('/proc/sys/net/ipv4/ip_forward').read_text().strip() != '1':
        parser.error('IPv4 forwarding is disabled. Configure it persistently before installing.')
    for name in (wan, wg):
        if not (Path('/sys/class/net') / name).exists():
            parser.error('Network interface does not exist: ' + name)
    path = Path('/usr/local/sbin/teslatalk-voice-forward')
    unit_path = Path('/etc/systemd/system/teslatalk-voice-forward.service')
    sysctl_path = Path('/etc/sysctl.d/95-teslatalk-voice-forward.conf')
    sysctl = '# Managed by TeslaTalk setup_voice_vps.py.\nnet.ipv4.ip_forward=1\n'
    unit = UNIT.replace('wg-quick@wg0.service', 'wg-quick@' + wg + '.service')
    for target, content in [(path, program), (unit_path, unit), (sysctl_path, sysctl)]:
        if target.exists() and target.read_text() != content:
            parser.error('An existing forwarding installation differs. Disable/remove it before changing its targets: ' + str(target))
    path.write_text(program)
    path.chmod(0o700)
    unit_path.write_text(unit)
    unit_path.chmod(0o644)
    sysctl_path.write_text(sysctl)
    sysctl_path.chmod(0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', 'teslatalk-voice-forward.service'], check=True)
    subprocess.run(['systemctl', 'restart', 'teslatalk-voice-forward.service'], check=True)
    print('Installed forwarding: ' + public + ':7881/TCP and :7882/UDP -> ' + home + ' via ' + wg)
    print('Only these ports are allowed. Existing firewall rules and policies are preserved.')
    print('After manually reloading a firewall: systemctl reload teslatalk-voice-forward.service')
    print('Undo: systemctl disable --now teslatalk-voice-forward.service')


if __name__ == '__main__':
    main()
