"""Ask a business's mail server whether a mailbox exists, without sending anything.

This is how the free email checkers work: Recon opens a conversation with the
mail server, says who it is, names the address as if about to send, notes the
answer, then says goodbye before any message is sent.

Being polite about it:
- Off unless you give --smtp-from with a real address of yours, so the server
  knows who is asking.
- One conversation at a time, a pause between them, and at most four
  addresses asked about per business.
- It first asks about a made-up address. If the server says yes to that, it
  says yes to everything ("catch-all"), and Recon records that rather than
  pretending to know.
- Google and Microsoft run the mail for a great many small businesses, often
  answer vaguely, and can block a sender who asks too often, so Recon leaves
  at least ten seconds between conversations with either.
- Many home and cloud connections block the mail port (25). If the first few
  tries cannot connect, Recon stops trying and says so. Run this step later
  from a small rented server with port 25 open; nothing else needs it.
"""

import random
import smtplib
import socket
import string
import time

MAX_PER_DOMAIN = 4
PAUSE = 1.0
TIMEOUT = 15
BIG_PROVIDERS = {"google.com": 10.0, "googlemail.com": 10.0, "outlook.com": 10.0}
BLOCKED_WORDS = ("block", "spam", "policy", "denied", "reputation", "listed", "banned")

SAFE, RISKY, INVALID, UNKNOWN = "safe", "risky", "invalid", "unknown"


def _made_up(domain):
    letters = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"recon-check-{letters}@{domain}"


def provider(host):
    """'aspmx.l.google.com' -> 'google.com': who runs a mail server."""
    return ".".join(host.lower().rstrip(".").split(".")[-2:])


def _answer(code, message):
    if code in (250, 251):
        return SAFE, "the mail server says this mailbox exists"
    text = (message or b"").decode("utf-8", "replace").lower()
    if 500 <= code < 600 and not any(word in text for word in BLOCKED_WORDS):
        return INVALID, "the mail server says this mailbox does not exist"
    return UNKNOWN, "the mail server would not say"


class Checker:
    def __init__(self, mail_from, helo=None, connect=smtplib.SMTP, pause=PAUSE):
        self.mail_from = mail_from
        self.helo = helo or socket.getfqdn()
        self.connect = connect
        self.pause = pause
        self.connected = 0
        self.failed = 0
        self.blocked = False
        self.last_seen = {}  # Provider -> when we last spoke to it.

    def check(self, domain, hosts, addresses):
        """{address: (result, reason)} for addresses on one domain."""
        addresses = list(dict.fromkeys(addresses))[:MAX_PER_DOMAIN]
        unknown = {a: (UNKNOWN, "could not reach the mail server") for a in addresses}
        if self.blocked or not hosts or not addresses:
            return unknown
        for host in hosts[:2]:
            self._wait(host)
            try:
                server = self.connect(host, 25, timeout=TIMEOUT)
            except (OSError, smtplib.SMTPException):
                self.failed += 1
                if self.failed >= 3 and not self.connected:
                    self.blocked = True
                    print("  Cannot reach any mail server on port 25 from this connection; "
                          "mailbox checks are off for the rest of the run")
                    return unknown
                continue
            self.connected += 1
            try:
                return self._talk(server, domain, addresses) or unknown
            except (OSError, smtplib.SMTPException):
                return unknown
            finally:
                try:
                    server.quit()
                except (OSError, smtplib.SMTPException):
                    pass
        return unknown

    def _wait(self, host):
        """Pause before speaking to a mail server, longer for the big providers."""
        name = provider(host)
        gap = max(self.pause, BIG_PROVIDERS.get(name, 0) if self.pause else 0)
        since = time.monotonic() - self.last_seen.get(name, -gap)
        if since < gap:
            time.sleep(gap - since)
        self.last_seen[name] = time.monotonic()

    def _talk(self, server, domain, addresses):
        server.ehlo(self.helo)
        code, _ = server.mail(self.mail_from)
        if code != 250:
            return None
        code, message = server.rcpt(_made_up(domain))
        if code in (250, 251):
            return {a: (RISKY, "the mail server accepts any address, so it cannot confirm this one")
                    for a in addresses}
        if _answer(code, message)[0] == UNKNOWN:
            return None  # It would not answer even about a made-up address.
        return {a: _answer(*server.rcpt(a)) for a in addresses}
