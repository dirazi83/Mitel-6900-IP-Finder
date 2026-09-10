#!/usr/bin/env python3
"""Mitel 6900-series phone discovery engine.

Standard library only: no Nmap, no Npcap, no scapy, no admin rights.

How it finds phones
-------------------
1. TCP sweep of the subnet on the phone web ports. Every connection attempt
   forces the OS to ARP-resolve on-link hosts, so the ARP cache fills up even
   for hosts that keep their web port closed.
2. The ARP cache is read back with `arp -a` and each IP is mapped to a MAC.
3. Hosts are fingerprinted over HTTP/HTTPS. A Mitel 6900 answers with
   `Server: Aragorn` and `WWW-Authenticate: Basic realm="Mitel 6915"`, which
   names the exact model.
4. Optional SIP OPTIONS probe on UDP 5060 returns a User-Agent such as
   `Mitel-6920-SIP/6.4.0.140` (model plus firmware).

MAC-prefix matching is kept as a filter, but a web or SIP signature is far
stronger evidence: MAC discovery only works on the same Ethernet/VLAN, while
HTTP/SIP fingerprints also work through a router.
"""
from __future__ import annotations

import concurrent.futures
import http.client
import ipaddress
import random
import re
import socket
import ssl
import subprocess
import threading

__version__ = '1.0.2'

# Registered Mitel OUIs (IEEE) plus prefixes seen on Aastra-era and
# contract-manufactured 6900 hardware. Keys are lowercase, no separators.
KNOWN_OUIS = {
    '08000f': 'Mitel Corporation',
    '00085d': 'Mitel (Aastra)',
    '0010bb': 'Aastra',
    '00e081': 'Aastra/Tyan',
    '001ae8': 'Unify/Siemens',
    '0004f2': 'Polycom',
}

WEB_PORTS = (80, 443)
SIP_PORT = 5060
DEFAULT_MAC_PREFIXES = ('14',)

MODEL_RE = re.compile(r'\b(6[0-9]{3}[wi]?|53[0-9]{2}e?)\b', re.I)
REALM_RE = re.compile(r'realm\s*=\s*"([^"]*)"', re.I)
TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
BRAND_RE = re.compile(r'\b(mitel|aastra|aragorn|minet)\b', re.I)
ARP_RE = re.compile(
    r'(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})')

FIELDS = ['IP address', 'MAC address', 'Vendor', 'Model', 'Firmware',
          'Ports', 'Evidence']

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def _run(command):
    """Run a local helper command and return stdout, or '' on failure."""
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                errors='replace', timeout=30,
                                creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return ''
    return result.stdout or ''


def normalize_mac(mac):
    return re.sub(r'[^0-9a-f]', '', (mac or '').lower())


def format_mac(mac):
    digits = normalize_mac(mac)
    if len(digits) != 12:
        return mac or ''
    return ':'.join(digits[i:i + 2] for i in range(0, 12, 2))


def vendor_for(mac):
    return KNOWN_OUIS.get(normalize_mac(mac)[:6], '')


def default_route_alias():
    """Interface alias carrying the default route, or '' if unknown."""
    script = ("(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
              "Sort-Object RouteMetric | Select-Object -First 1).InterfaceAlias")
    return _run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script]).strip()


def local_networks():
    """Return [(cidr, interface_alias)], default-route interface first."""
    script = ("Get-NetIPAddress -AddressFamily IPv4 | "
              "Where-Object { $_.PrefixLength -lt 31 -and $_.IPAddress -ne '127.0.0.1' } | "
              "ForEach-Object { $_.IPAddress + '/' + $_.PrefixLength + ' ' + $_.InterfaceAlias }")
    output = _run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script])
    networks = []
    for line in output.splitlines():
        parts = line.split(None, 1)
        if not parts:
            continue
        try:
            network = ipaddress.ip_network(parts[0], strict=False)
        except ValueError:
            continue
        if network.num_addresses > 4096:
            continue
        entry = (str(network), parts[1].strip() if len(parts) > 1 else '')
        if entry not in networks:
            networks.append(entry)
    preferred = default_route_alias()
    if preferred:
        networks.sort(key=lambda entry: entry[1] != preferred)
    return networks


def arp_table():
    """Parse the local ARP cache into {ip: mac}."""
    table = {}
    for line in _run(['arp', '-a']).splitlines():
        match = ARP_RE.search(line)
        if not match:
            continue
        ip, mac = match.group(1), normalize_mac(match.group(2))
        if mac in ('ffffffffffff', '000000000000') or ip.endswith('.255'):
            continue
        if ip.startswith(('224.', '239.', '255.')):
            continue
        table.setdefault(ip, mac)
    return table


def tcp_open(ip, port, timeout):
    """Connect-scan one port. The attempt also ARPs the host when on-link."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            return sock.connect_ex((ip, port)) == 0
        except OSError:
            return False


def http_probe(ip, port, timeout):
    """GET / and return {status, server, realm, title} for a web port."""
    info = {}
    try:
        if port == 443:
            context = ssl._create_unverified_context()
            connection = http.client.HTTPSConnection(ip, port, timeout=timeout,
                                                     context=context)
        else:
            connection = http.client.HTTPConnection(ip, port, timeout=timeout)
        try:
            connection.request('GET', '/', headers={
                'User-Agent': 'mitel-finder/2.0', 'Connection': 'close'})
            response = connection.getresponse()
            info['status'] = response.status
            info['server'] = response.getheader('Server', '') or ''
            authenticate = response.getheader('WWW-Authenticate', '') or ''
            realm = REALM_RE.search(authenticate)
            info['realm'] = realm.group(1) if realm else ''
            body = response.read(4096).decode('utf-8', 'replace')
            title = TITLE_RE.search(body)
            info['title'] = title.group(1).strip() if title else ''
        finally:
            connection.close()
    except (OSError, http.client.HTTPException, ssl.SSLError, ValueError):
        return {}
    return info


def sip_probe(ip, timeout):
    """Send one SIP OPTIONS and return the responding User-Agent/Server."""
    tag = '%08x' % random.getrandbits(32)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((ip, SIP_PORT))
            source_ip, source_port = sock.getsockname()
        except OSError:
            return ''
        request = '\r\n'.join([
            'OPTIONS sip:%s SIP/2.0' % ip,
            'Via: SIP/2.0/UDP %s:%s;branch=z9hG4bK%s;rport' % (source_ip, source_port, tag),
            'Max-Forwards: 70',
            'From: <sip:discovery@%s>;tag=%s' % (source_ip, tag),
            'To: <sip:%s>' % ip,
            'Call-ID: %s@%s' % (tag, source_ip),
            'CSeq: 1 OPTIONS',
            'Contact: <sip:discovery@%s:%s>' % (source_ip, source_port),
            'Accept: application/sdp',
            'Content-Length: 0', '', '',
        ])
        try:
            sock.send(request.encode('ascii'))
            data = sock.recv(4096).decode('utf-8', 'replace')
        except OSError:
            return ''
    for line in data.splitlines():
        if line.lower().startswith(('user-agent:', 'server:')):
            return line.split(':', 1)[1].strip()
    return ''


def split_model_firmware(text):
    """'Mitel-6920-SIP/6.4.0.140' -> ('6920', '6.4.0.140')."""
    if not text:
        return '', ''
    model = MODEL_RE.search(text)
    version = re.search(r'(\d+\.\d+[\d.]*)', text.split('/', 1)[1]) if '/' in text else None
    return (model.group(1) if model else '', version.group(1) if version else '')


def expand_targets(text):
    """Accept '10.0.2.0/24', '10.0.2.10-60', or a single IP."""
    text = text.strip()
    if '-' in text:
        start, _, end = text.partition('-')
        first = ipaddress.ip_address(start.strip())
        last_part = end.strip()
        if '.' not in last_part:
            last_part = start.strip().rsplit('.', 1)[0] + '.' + last_part
        last = ipaddress.ip_address(last_part)
        if int(last) < int(first):
            raise ValueError('Range end is before the range start.')
        if int(last) - int(first) > 65535:
            raise ValueError('Scan at most 65536 addresses at a time.')
        return [str(ipaddress.ip_address(value))
                for value in range(int(first), int(last) + 1)]
    network = ipaddress.ip_network(text, strict=False)
    if network.version != 4:
        raise ValueError('Provide an IPv4 subnet, range, or address.')
    if network.num_addresses > 65536:
        raise ValueError('Scan a /16 or smaller subnet at a time.')
    if network.prefixlen >= 31:
        return [str(network.network_address)]
    return [str(host) for host in network.hosts()]


class Scanner:
    """Two-phase scan: ARP-filling TCP sweep, then HTTP/SIP fingerprinting."""

    def __init__(self, targets, mac_prefixes=DEFAULT_MAC_PREFIXES,
                 deep_probe=True, sip=True, timeout=0.5, workers=128,
                 mac_only=False):
        self.targets = list(targets)
        self.mac_prefixes = tuple(p for p in
                                  (normalize_mac(prefix) for prefix in mac_prefixes) if p)
        self.deep_probe = deep_probe
        self.sip = sip
        self.timeout = timeout
        self.workers = max(1, min(workers, 256))
        self.mac_only = mac_only
        self.hosts_seen = 0
        self.macs_seen = 0
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def _sweep_one(self, ip):
        ports = [port for port in WEB_PORTS if tcp_open(ip, port, self.timeout)]
        return ip, ports

    def run(self, on_progress=None, on_row=None, on_message=None):
        """Run the scan, reporting through callbacks, and return the rows."""
        def notify(text):
            if on_message:
                on_message(text)

        def progress(done, total):
            if on_progress:
                on_progress(done, total)

        total = len(self.targets)
        notify('Sweeping %d address(es) on TCP %s...'
               % (total, ', '.join(str(port) for port in WEB_PORTS)))
        open_ports = {}
        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = [pool.submit(self._sweep_one, ip) for ip in self.targets]
            for future in concurrent.futures.as_completed(futures):
                if self._cancel.is_set():
                    for pending in futures:
                        pending.cancel()
                    break
                done += 1
                ip, ports = future.result()
                if ports:
                    open_ports[ip] = ports
                progress(done, total)
        if self._cancel.is_set():
            return []

        notify('Reading ARP cache...')
        arp = arp_table()
        targets = set(self.targets)
        self.macs_seen = sum(1 for ip in arp if ip in targets)
        self.hosts_seen = len(set(open_ports) | {ip for ip in arp if ip in targets})

        candidates = []
        for ip in sorted(targets, key=ipaddress.ip_address):
            mac = arp.get(ip, '')
            prefix_match = bool(mac) and bool(self.mac_prefixes) and mac.startswith(self.mac_prefixes)
            oui_match = bool(vendor_for(mac))
            web_candidate = ip in open_ports and not self.mac_only
            if prefix_match or oui_match or web_candidate:
                candidates.append((ip, mac, prefix_match, oui_match))

        notify('Fingerprinting %d candidate host(s)...' % len(candidates))
        rows = []
        probe_timeout = max(self.timeout * 4, 2.0)
        for index, (ip, mac, prefix_match, oui_match) in enumerate(candidates, 1):
            if self._cancel.is_set():
                break
            ports = open_ports.get(ip, [])
            evidence, model, firmware, signature = [], '', '', ''
            if prefix_match:
                evidence.append('MAC prefix %s' % format_mac(mac)[:5])
            if oui_match:
                evidence.append('OUI: %s' % vendor_for(mac))

            if self.deep_probe:
                for port in ports:
                    info = http_probe(ip, port, probe_timeout)
                    if not info:
                        continue
                    blob = ' '.join(part for part in (info.get('server', ''),
                                                      info.get('realm', ''),
                                                      info.get('title', '')) if part)
                    if BRAND_RE.search(blob):
                        signature = blob.strip()
                        evidence.append('web signature (%d)' % port)
                        found = MODEL_RE.search(blob)
                        if found:
                            model = found.group(1)
                        break
                if self.sip and not model:
                    agent = sip_probe(ip, probe_timeout)
                    if agent and BRAND_RE.search(agent):
                        sip_model, sip_version = split_model_firmware(agent)
                        model = model or sip_model
                        firmware = firmware or sip_version
                        signature = signature or agent
                        evidence.append('SIP OPTIONS reply')

            confirmed = any(item.startswith(('web signature', 'SIP')) for item in evidence)
            if not (confirmed or prefix_match or oui_match):
                continue

            row = dict(zip(FIELDS, [
                ip,
                format_mac(mac) or '-',
                vendor_for(mac) or ('Mitel candidate (MAC prefix)' if prefix_match else '-'),
                model or '-',
                firmware or '-',
                ','.join(str(port) for port in ports) or '-',
                '; '.join(evidence) + (' [%s]' % signature if signature else ''),
            ]))
            rows.append(row)
            if on_row:
                on_row(row)
            progress(total + index, total + len(candidates))
        return rows
