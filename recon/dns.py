"""Ask whether a domain accepts email, using only the standard library.

Python has no built-in way to look up mail (MX) records, so this sends the
small DNS question itself: the same thing `dig example.co.uk MX` does. It asks
the computer's own resolver first and falls back to public ones. Where a
network blocks ordinary DNS, it asks Google's public resolver over HTTPS
instead (or always, if RECON_DNS_OVER_HTTPS=1).
"""

import base64
import os
import random
import socket
import struct
import urllib.request

PUBLIC_RESOLVERS = ("1.1.1.1", "8.8.8.8")
OVER_HTTPS = "https://dns.google/dns-query?dns="
TIMEOUT = 4
MX, A = 15, 1

# What mail_server() says, in plain words for the spreadsheet.
YES = "yes"
NO = "no"
UNKNOWN = "unknown"


def query(name, qtype, ident=None):
    """The bytes of a DNS question asking for one record type."""
    ident = random.randint(0, 0xFFFF) if ident is None else ident
    header = struct.pack(">HHHHHH", ident, 0x0100, 1, 0, 0, 0)  # Recursion wanted.
    labels = b"".join(bytes([len(part)]) + part.encode("idna")
                      for part in name.strip(".").split("."))
    return header + labels + b"\x00" + struct.pack(">HH", qtype, 1)


def _name(data, offset):
    """Read a possibly compressed name; return it and where the record carries on."""
    parts, jumped, end = [], False, offset
    for _ in range(64):  # Guards against a looping pointer in a broken reply.
        length = data[offset]
        if length & 0xC0 == 0xC0:
            if not jumped:
                end = offset + 2
            offset = ((length & 0x3F) << 8) | data[offset + 1]
            jumped = True
            continue
        if length == 0:
            return ".".join(parts), (end if jumped else offset + 1)
        parts.append(data[offset + 1:offset + 1 + length].decode("ascii", "replace"))
        offset += 1 + length
    raise ValueError("DNS name too long")


def parse(data):
    """(error code, truncated, answers) where answers are (type, value) pairs.

    Error code 0 means the question was answered; 3 means no such domain.
    MX answers come back as (preference, host).
    """
    _, flags, questions, answers, _, _ = struct.unpack(">HHHHHH", data[:12])
    offset = 12
    for _ in range(questions):
        _, offset = _name(data, offset)
        offset += 4
    found = []
    for _ in range(answers):
        _, offset = _name(data, offset)
        rtype, _, _, length = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        if rtype == MX:
            preference = struct.unpack(">H", data[offset:offset + 2])[0]
            host, _ = _name(data, offset + 2)
            found.append((MX, (preference, host.lower())))
        elif rtype == A and length == 4:
            found.append((A, socket.inet_ntoa(data[offset:offset + 4])))
        offset += length
    return flags & 0x000F, bool(flags & 0x0200), found


def resolvers():
    """The computer's own resolvers (from /etc/resolv.conf), then public ones."""
    found = []
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "nameserver" and ":" not in parts[1]:
                    found.append(parts[1])
    except OSError:
        pass
    return found + [r for r in PUBLIC_RESOLVERS if r not in found]


def _ask(server, packet):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT)
        sock.sendto(packet, (server, 53))
        reply = sock.recv(4096)
    if parse(reply)[1]:  # Too long for one packet: ask again over TCP.
        with socket.create_connection((server, 53), timeout=TIMEOUT) as sock:
            sock.sendall(struct.pack(">H", len(packet)) + packet)
            size = struct.unpack(">H", sock.recv(2))[0]
            reply = b""
            while len(reply) < size:
                chunk = sock.recv(size - len(reply))
                if not chunk:
                    break
                reply += chunk
    return reply


def _ask_over_https(packet):
    url = OVER_HTTPS + base64.urlsafe_b64encode(packet).decode().rstrip("=")
    request = urllib.request.Request(url, headers={"Accept": "application/dns-message"})
    with urllib.request.urlopen(request, timeout=TIMEOUT * 2) as response:
        return response.read(65535)


def lookup(name, qtype, servers=None):
    """(error code, answers) from the first resolver that replies, or (None, [])."""
    packet = query(name, qtype)
    asks = [] if os.environ.get("RECON_DNS_OVER_HTTPS") == "1" else [
        (lambda server=server: _ask(server, packet)) for server in servers or resolvers()]
    if servers is None:
        asks.append(lambda: _ask_over_https(packet))
    for ask in asks:
        try:
            code, _, answers = parse(ask())
            return code, answers
        except (OSError, ValueError, struct.error, IndexError):
            continue
    return None, []


def mx_hosts(domain, servers=None):
    """The domain's mail servers, best first.

    Returns (status, hosts): status is YES, NO (the domain does not exist or
    has no way to receive mail) or UNKNOWN (no resolver answered).
    """
    code, answers = lookup(domain, MX, servers)
    if code is None:
        return UNKNOWN, []
    if code == 3:
        return NO, []
    hosts = [host for _, (pref, host) in sorted(
        (a for a in answers if a[0] == MX), key=lambda a: a[1][0])]
    if hosts in ([""], ["."]):
        return NO, []  # A "null MX" says the domain never takes mail.
    if hosts:
        return YES, hosts
    # No MX record: mail goes to the domain's own address, if it has one.
    code, answers = lookup(domain, A, servers)
    if code is None:
        return UNKNOWN, []
    return (YES, [domain]) if any(a[0] == A for a in answers) else (NO, [])


class Cache:
    """Remember each domain's answer for the length of a run."""

    def __init__(self, servers=None):
        self.servers = servers
        self.known = {}

    def __call__(self, domain):
        domain = domain.lower()
        if domain not in self.known:
            self.known[domain] = mx_hosts(domain, self.servers)
        return self.known[domain]

