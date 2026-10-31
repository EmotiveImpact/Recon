"""Calling from Recon, prepared for VoIPstudio but switched off until Edem
signs up and sets the keys.

How it will work (research in the "Calling platform research" thread, 16
October 2026: VoIPstudio's 2K bundle, about £15 a month, 2,000 UK minutes, a
UK number, REST API and webhooks):

1. Today's calls shows a Call button beside each business. Pressing it asks
   VoIPstudio to ring the business from Edem's VoIPstudio user (the app or
   desk phone rings first, then the business), and Recon notes the attempt.
2. VoIPstudio tells Recon when the call rings, connects and hangs up, by
   calling back the webhook address; Recon stores how long the call ran and
   where the recording is, against the business.
3. Edem presses an outcome button (no answer, spoke, call back ...).

Before any number is dialled, Recon checks that the business is not on the
do-not-contact list and that its number was screened against the TPS and
CTPS within the last 28 days (docs/RULES.md). Without a clear screening the
button stays off and says why.

Settings come from the environment, never from a file in the repository:
  RECON_VOIPSTUDIO_TOKEN      the API key from VoIPstudio's dashboard
  RECON_VOIPSTUDIO_USER       Edem's VoIPstudio user id (whose phone rings first)
  RECON_VOIPSTUDIO_CALLER_ID  the UK number to show, digits only
  RECON_VOIPSTUDIO_URL        the API address (default https://l7api.com/v1.2/voipstudio)
  RECON_WEBHOOK_KEY           a secret VoIPstudio must put in the webhook address
  RECON_ALLOW_UNSCREENED=1    only for a test call to Edem's own phone
"""

import json
import os
import urllib.error
import urllib.request

from . import crm as crm_module

DEFAULT_URL = "https://l7api.com/v1.2/voipstudio"

# VoIPstudio's webhook event names (its "Call State Change" events) and what
# Recon writes down for each.
EVENTS = {
    "call.ringing": "ringing",
    "call.connected": "connected",
    "call.hangup": "ended",
    "call.missed": "no answer",
    "call.recording": "recording ready",
}


class Calling:
    def __init__(self, crm, env=None, opener=None):
        self.crm = crm
        self.env = os.environ if env is None else env
        self.opener = opener or urllib.request.urlopen

    @property
    def token(self):
        return self.env.get("RECON_VOIPSTUDIO_TOKEN", "").strip()

    @property
    def configured(self):
        return bool(self.token)

    def setup(self):
        """What the Today's calls page shows about calling."""
        missing = [name for name in ("RECON_VOIPSTUDIO_TOKEN", "RECON_VOIPSTUDIO_USER")
                   if not self.env.get(name, "").strip()]
        return {
            "provider": "VoIPstudio",
            "configured": self.configured,
            "missing": missing,
            "webhook_protected": bool(self.env.get("RECON_WEBHOOK_KEY", "").strip()),
            "caller_id": self.env.get("RECON_VOIPSTUDIO_CALLER_ID", "").strip(),
            "unscreened": len(self.crm.unscreened()),
            "steps": [
                "Sign up for VoIPstudio (30-day free trial, 2K bundle) and add a UK number.",
                "In VoIPstudio's dashboard, add an API key for your user and copy your user id.",
                "Start Recon's server with RECON_VOIPSTUDIO_TOKEN, RECON_VOIPSTUDIO_USER and "
                "RECON_VOIPSTUDIO_CALLER_ID set.",
                "In VoIPstudio, Integrations, Webhooks: add Recon's address "
                "/api/calls/webhook?key=... for the Call State Change and Call Recording Ready events.",
                "Run the day's numbers through a TPS/CTPS check and import the results "
                "(python -m recon.crm screen results.csv).",
            ],
        }

    def check(self, bid):
        """Why this business may not be rung right now, or '' when it may."""
        found = self.crm.business(bid)
        if found["blocked"] or found["status"] == "do not contact":
            return "This business asked not to be contacted."
        number = crm_module.normalise_phone(found["phone"] or found["mobile"], found["country"])
        if not number:
            return "Recon has no phone number for this business."
        screening = found["screening"]
        if screening in ("tps", "ctps"):
            return f"This number is on the {screening.upper()} register, so it may not be called."
        if screening in ("unknown", "stale") and self.env.get("RECON_ALLOW_UNSCREENED") != "1":
            return ("This number has not been checked against the TPS and CTPS in the last 28 days. "
                    "Run the check and import the results first.")
        if not self.configured:
            return "Calling is not switched on yet: VoIPstudio's keys are not set."
        return ""

    def start(self, bid):
        """Ask VoIPstudio to ring the business, and note the attempt."""
        reason = self.check(bid)
        if reason:
            raise ValueError(reason)
        found = self.crm.business(bid)
        number = crm_module.normalise_phone(found["phone"] or found["mobile"], found["country"])
        body = {"to": number.lstrip("+")}
        user = self.env.get("RECON_VOIPSTUDIO_USER", "").strip()
        caller = self.env.get("RECON_VOIPSTUDIO_CALLER_ID", "").strip().lstrip("+")
        if user:
            body["from"] = user
        if caller:
            body["caller_id"] = caller
        reply = self._request("POST", "/calls", body)
        call_id = str((reply.get("data") or {}).get("id") or reply.get("id") or "")
        self.crm.log(bid, "note", note=f"Call started to {number}", call_id=call_id, kind="call")
        return {"call_id": call_id, "to": number, "business": bid}

    def webhook(self, payload, key=""):
        """What VoIPstudio tells us about a call. Returns what was recorded."""
        expected = self.env.get("RECON_WEBHOOK_KEY", "").strip()
        if expected and key != expected:
            raise PermissionError("Wrong webhook key")
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        event = str(payload.get("event") or payload.get("type") or "").lower()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        call_id = str(data.get("call_id") or data.get("id") or payload.get("call_id") or "")
        what = EVENTS.get(event, event or "event")
        bid = self._business_for(call_id, data)
        if not bid:
            return {"recorded": False, "event": what, "call_id": call_id}
        seconds = None
        for key_name in ("duration", "billsec", "talk_time", "seconds"):
            if data.get(key_name) not in (None, ""):
                try:
                    seconds = int(float(data[key_name]))
                except (TypeError, ValueError):
                    seconds = None
                break
        recording = str(data.get("recording_url") or data.get("recording") or data.get("url") or "")
        if what in ("ringing", "connected"):
            return {"recorded": False, "event": what, "call_id": call_id, "business": bid}
        note = {"ended": "Call ended", "no answer": "No answer",
                "recording ready": "Recording ready"}.get(what, what.capitalize())
        if seconds is not None and what == "ended":
            note += f" after {seconds} seconds"
        self.crm.log(bid, "note", note=note, seconds=seconds, recording=recording, call_id=call_id,
                     kind="call")
        return {"recorded": True, "event": what, "call_id": call_id, "business": bid,
                "seconds": seconds}

    def _business_for(self, call_id, data):
        """The business a VoIPstudio call belongs to: the one Recon started with
        that call id, or the one whose number was dialled."""
        if call_id:
            row = self.crm._one("SELECT business FROM activities WHERE call_id = ? ORDER BY id DESC",
                                (call_id,))
            if row:
                return row["business"]
        for key_name in ("dst", "to", "destination", "callee", "number"):
            number = crm_module.normalise_phone(data.get(key_name))
            if not number:
                continue
            for row in self.crm._rows("SELECT id, phone, mobile, country FROM businesses"):
                if number in (crm_module.normalise_phone(row["phone"], row["country"]),
                              crm_module.normalise_phone(row["mobile"], row["country"])):
                    return row["id"]
        return None

    def _request(self, method, path, body=None):
        url = self.env.get("RECON_VOIPSTUDIO_URL", "").strip() or DEFAULT_URL
        request = urllib.request.Request(
            url.rstrip("/") + path, method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"X-Auth-Token": self.token, "Content-Type": "application/json",
                     "Accept": "application/json"})
        try:
            with self.opener(request, timeout=20) as response:
                text = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise ValueError(f"VoIPstudio said {error.code}: {detail or error.reason}") from None
        except (urllib.error.URLError, OSError) as error:
            raise ValueError(f"Could not reach VoIPstudio: {error}") from None
        try:
            return json.loads(text) if text else {}
        except ValueError:
            return {"raw": text[:300]}
