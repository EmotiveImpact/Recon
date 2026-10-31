"""Offline tests for the small CRM (recon/crm.py) and the calling hook-up
(recon/calling.py). Nothing here touches the network or dials anything."""

import datetime as dt
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import threading

from recon import calling, crm, server


def rows():
    return [
        {"group_id": "g1", "name": "Glow Room", "phones": "0113 111 1111; 07700 900001",
         "emails": "hi@glow.co.uk", "can_email": "can email", "website": "glow.co.uk",
         "postcode": "LS1 1AA", "kind": "company; hair salon", "sources": "companies-house"},
        {"group_id": "g2", "name": "Jo Nails", "phones": "07700 900002", "can_email": "post only",
         "postcode": "LS1 2BB", "kind": "nail salon"},
        {"name": "Trade Co", "company_number": "123", "phone": "01132223333",
         "contact_rule": "can email", "postcode": "LS2 3CC", "trade": "plumbers"},
        {"group_id": "g4", "name": "No Phone Ltd", "emails": "a@b.co.uk", "can_email": "can email"},
    ]


class PhoneTests(unittest.TestCase):
    def test_uk_numbers_become_international(self):
        self.assertEqual(crm.normalise_phone("0113 111 1111"), "+441131111111")
        self.assertEqual(crm.normalise_phone("+44 (0)7700 900001"), "+447700900001")
        self.assertEqual(crm.normalise_phone("00447700900001"), "+447700900001")
        self.assertEqual(crm.normalise_phone("07700 900001; 0113 1"), "+447700900001")
        self.assertEqual(crm.normalise_phone("(512) 555-0100", "US"), "+15125550100")
        self.assertEqual(crm.normalise_phone("not a number"), "")
        self.assertEqual(crm.normalise_phone(""), "")
        self.assertTrue(crm.is_mobile("+447700900001"))
        self.assertFalse(crm.is_mobile("+441131111111"))

    def test_a_business_keeps_one_id(self):
        self.assertEqual(crm.business_id({"group_id": "x:1"}), "x:1")
        self.assertEqual(crm.business_id({"name": "A", "company_number": "9"}), "trade:9")
        self.assertEqual(crm.business_id({"name": " Glow  Room ", "postcode": "ls1 1aa"}), "trade:glow room|LS11AA")
        with self.assertRaises(ValueError):
            crm.business_id({})


class CRMTests(unittest.TestCase):
    def setUp(self):
        self.crm = crm.CRM(":memory:")
        self.list_id = self.crm.create_list("Salons in Leeds", "SALEANE", query={"sector": ["beauty"]})
        self.crm.add_items(self.list_id, rows())

    def test_lists_count_their_businesses(self):
        found = self.crm.lists()
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["businesses"], found[0]["with_phone"], found[0]["may_email"], found[0]["contacted"]),
                         (4, 3, 3, 0))
        detail = self.crm.get_list(self.list_id)
        self.assertEqual(detail["query"], {"sector": ["beauty"]})
        glow = next(i for i in detail["items"] if i["id"] == "g1")
        self.assertEqual((glow["phone"], glow["mobile"], glow["email"], glow["rule"], glow["kind"], glow["status"]),
                         ("0113 111 1111", "07700 900001", "hi@glow.co.uk", "can email", "company", "new"))

    def test_adding_twice_adds_once_and_keeps_what_was_known(self):
        self.assertEqual(self.crm.add_items(self.list_id, [{"group_id": "g1", "name": "Glow Room", "phones": ""}]), 0)
        self.assertEqual(self.crm.business("g1")["phone"], "0113 111 1111")
        other = self.crm.create_list("Second")
        self.assertEqual(self.crm.add_items(other, rows()[:1]), 1)
        self.assertEqual(self.crm.summary()["businesses"], 4)

    def test_todays_calls_put_the_best_prospects_first_and_skip_the_finished(self):
        names = [c["name"] for c in self.crm.today_calls(self.list_id)]
        self.assertEqual(names, ["Glow Room", "Trade Co", "Jo Nails"])  # No Phone Ltd has no phone.
        first = self.crm.today_calls(self.list_id)[0]
        self.assertEqual(first["dial"], "+441131111111")
        self.assertEqual(first["screening"], "unknown")
        self.assertIn("has a website", first["why"])
        self.crm.log("g1", "not interested")
        self.crm.log("g2", "customer")
        self.assertEqual([c["name"] for c in self.crm.today_calls(self.list_id)], ["Trade Co"])

    def test_a_business_rung_today_waits_until_tomorrow(self):
        self.crm.log("g1", "no answer")
        self.assertNotIn("Glow Room", [c["name"] for c in self.crm.today_calls(self.list_id)])
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        later = self.crm.today_calls(self.list_id, day=tomorrow)
        self.assertEqual([c["name"] for c in later], ["Trade Co", "Jo Nails", "Glow Room"])
        self.assertIn("no answer so far (1 tries)", later[-1]["why"])

    def test_call_backs_come_first_when_due(self):
        soon = (dt.date.today() + dt.timedelta(days=2)).isoformat()
        self.crm.log("g2", "call back", "Ask for Jo", call_back=soon)
        self.assertNotIn("Jo Nails", [c["name"] for c in self.crm.today_calls(self.list_id)])
        due = self.crm.today_calls(self.list_id, day=soon)
        self.assertEqual(due[0]["name"], "Jo Nails")
        self.assertEqual(due[0]["why"], "call back due today")
        self.assertEqual(self.crm.business("g2")["note"], "Ask for Jo")
        with self.assertRaises(ValueError):
            self.crm.log("g2", "call back")
        with self.assertRaises(ValueError):
            self.crm.log("g2", "call back", call_back="next week")

    def test_notes_pile_up_and_outcomes_move_the_status(self):
        self.crm.log("g1", "note", "Owner is Sam")
        self.crm.log("g1", "note", "Open Tuesdays")
        found = self.crm.business("g1")
        self.assertEqual(found["note"], "Owner is Sam\nOpen Tuesdays")
        self.assertEqual(found["status"], "new")
        self.crm.log("g1", "interested", "Wants a demo")
        found = self.crm.business("g1")
        self.assertEqual((found["status"], found["note"]), ("interested", "Wants a demo"))
        self.assertEqual([h["outcome"] for h in found["history"]], ["interested", "", ""])
        with self.assertRaises(ValueError):
            self.crm.log("g1", "shouted")
        with self.assertRaises(LookupError):
            self.crm.log("nobody", "spoke")

    def test_do_not_contact_blocks_the_business_and_its_number_everywhere(self):
        self.crm.log("g2", "do not contact", "asked us to stop")
        blocked = self.crm.blocked()
        self.assertEqual((blocked[0]["business"], blocked[0]["phone"]), ("g2", "+447700900002"))
        self.assertTrue(self.crm.business("g2")["blocked"])
        # Another business with the same mobile is blocked too.
        self.crm.add_items(self.list_id, [{"group_id": "g5", "name": "Jo's Other Shop", "phones": "07700900002"}])
        self.assertTrue(self.crm.business("g5")["blocked"])
        self.assertNotIn("Jo's Other Shop", [c["name"] for c in self.crm.today_calls(self.list_id)])
        self.assertTrue(next(i for i in self.crm.get_list(self.list_id)["items"] if i["id"] == "g5")["blocked"])
        self.crm.block(email="HI@glow.co.uk", reason="letter")
        self.assertTrue(self.crm.business("g1")["blocked"])
        self.crm.unblock(blocked[0]["id"])
        self.assertFalse(self.crm.business("g2")["blocked"])
        with self.assertRaises(ValueError):
            self.crm.block()

    def test_screening_lasts_28_days(self):
        self.assertEqual(self.crm.unscreened(self.list_id), ["+441131111111", "+441132223333", "+447700900002"])
        saved = self.crm.record_screening([{"phone": "0113 111 1111", "result": "clear"},
                                           {"phone": "07700 900002", "result": "TPS"},
                                           {"phone": "", "result": "clear"}])
        self.assertEqual(saved, 2)
        by_name = {c["name"]: c["screening"] for c in self.crm.today_calls(self.list_id)}
        self.assertEqual(by_name, {"Glow Room": "clear", "Jo Nails": "tps", "Trade Co": "unknown"})
        old = (dt.date.today() - dt.timedelta(days=29)).isoformat()
        self.crm.record_screening([{"phone": "01132223333", "result": "clear"}], checked=old)
        self.assertEqual(self.crm.business("trade:123")["screening"], "stale")
        self.assertEqual(self.crm.unscreened(self.list_id), ["+441132223333"])
        self.assertEqual(self.crm.business("g4")["screening"], "no phone")

    def test_niches_keep_the_search(self):
        self.crm.save_niche("Salons in Leeds", {"sector": ["beauty"], "near": ["Leeds"], "has": ["email", "phone"], "empty": []})
        found = self.crm.niches()
        self.assertEqual(found[0]["query"], {"sector": ["beauty"], "near": ["Leeds"], "has": ["email", "phone"]})
        with self.assertRaises(ValueError):
            self.crm.save_niche("", {"sector": ["beauty"]})
        with self.assertRaises(ValueError):
            self.crm.save_niche("Nothing", {})
        self.crm.delete_niche(found[0]["id"])
        self.assertEqual(self.crm.niches(), [])

    def test_export_and_delete(self):
        folder = tempfile.mkdtemp()
        try:
            path = os.path.join(folder, "list.csv")
            self.crm.log("g1", "spoke", "Nice chat")
            self.assertEqual(self.crm.export_list(self.list_id, path), 4)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("Glow Room", text)
            self.assertIn("Nice chat", text)
        finally:
            shutil.rmtree(folder)
        self.crm.delete_list(self.list_id)
        self.assertEqual(self.crm.lists(), [])
        self.assertEqual(self.crm.business("g1")["status"], "spoke")  # Notes outlive the list.
        with self.assertRaises(LookupError):
            self.crm.get_list(self.list_id)


class FakeResponse:
    def __init__(self, request, sent):
        sent.append(request)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"data": {"id": 77, "state": 0}}'


class CallingTests(unittest.TestCase):
    def setUp(self):
        self.crm = crm.CRM(":memory:")
        self.list_id = self.crm.create_list("Leeds")
        self.crm.add_items(self.list_id, rows())
        self.sent = []
        self.env = {"RECON_VOIPSTUDIO_TOKEN": "secret", "RECON_VOIPSTUDIO_USER": "4321",
                    "RECON_VOIPSTUDIO_CALLER_ID": "+441132220000", "RECON_WEBHOOK_KEY": "hook"}
        self.calling = calling.Calling(self.crm, env=self.env,
                                       opener=lambda request, timeout: FakeResponse(request, self.sent))

    def test_switched_off_without_keys(self):
        off = calling.Calling(self.crm, env={})
        self.assertFalse(off.setup()["configured"])
        self.assertEqual(off.setup()["missing"], ["RECON_VOIPSTUDIO_TOKEN", "RECON_VOIPSTUDIO_USER"])
        self.crm.record_screening([{"phone": "0113 111 1111", "result": "clear"}])
        self.assertIn("not switched on", off.check("g1"))
        with self.assertRaises(ValueError):
            off.start("g1")

    def test_nobody_is_dialled_without_a_clear_screening(self):
        self.assertIn("not been checked", self.calling.check("g1"))
        self.crm.record_screening([{"phone": "07700 900002", "result": "ctps"}])
        self.assertIn("CTPS", self.calling.check("g2"))
        self.assertIn("no phone", self.calling.check("g4"))
        self.crm.log("trade:123", "do not contact")
        self.crm.record_screening([{"phone": "01132223333", "result": "clear"}])
        self.assertIn("asked not to be contacted", self.calling.check("trade:123"))
        self.assertEqual(self.sent, [])

    def test_a_call_goes_to_voipstudio_and_is_noted(self):
        self.crm.record_screening([{"phone": "0113 111 1111", "result": "clear"}])
        self.assertEqual(self.calling.check("g1"), "")
        result = self.calling.start("g1")
        self.assertEqual(result, {"call_id": "77", "to": "+441131111111", "business": "g1"})
        request = self.sent[0]
        self.assertEqual(request.full_url, "https://l7api.com/v1.2/voipstudio/calls")
        self.assertEqual(request.get_header("X-auth-token"), "secret")
        self.assertEqual(json.loads(request.data), {"to": "441131111111", "from": "4321", "caller_id": "441132220000"})
        history = self.crm.business("g1")["history"]
        self.assertEqual((history[0]["kind"], history[0]["call_id"]), ("call", "77"))
        self.assertEqual(self.crm.business("g1")["note"], "")  # The phone system's notes stay out of Edem's.
        # Rung today, so not offered again today.
        self.assertNotIn("Glow Room", [c["name"] for c in self.crm.today_calls(self.list_id)])

    def test_the_webhook_records_how_long_the_call_ran(self):
        self.crm.record_screening([{"phone": "0113 111 1111", "result": "clear"}])
        self.calling.start("g1")
        with self.assertRaises(PermissionError):
            self.calling.webhook({"event": "call.hangup"}, key="wrong")
        quiet = self.calling.webhook({"event": "call.ringing", "data": {"id": 77}}, key="hook")
        self.assertEqual(quiet["recorded"], False)
        done = self.calling.webhook({"event": "call.hangup", "data": {"id": 77, "duration": "95",
                                                                     "recording_url": "https://x/rec.mp3"}}, key="hook")
        self.assertEqual((done["recorded"], done["business"], done["seconds"]), (True, "g1", 95))
        latest = self.crm.business("g1")["history"][0]
        self.assertEqual((latest["seconds"], latest["recording"], latest["note"]),
                         (95, "https://x/rec.mp3", "Call ended after 95 seconds"))
        # A call Recon didn't start is matched by the number dialled.
        by_number = self.calling.webhook({"event": "call.hangup", "data": {"id": 78, "dst": "447700900002", "billsec": 12}}, key="hook")
        self.assertEqual(by_number["business"], "g2")
        unknown = self.calling.webhook({"event": "call.hangup", "data": {"id": 79, "dst": "441000000000"}}, key="hook")
        self.assertEqual(unknown["recorded"], False)


class CRMServerTests(unittest.TestCase):
    """The CRM through the website's own API."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "targets"))
        self.workspace = server.Workspace(self.root)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.handler_for(self.workspace, self.root))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.workspace.crm.db.close()
        shutil.rmtree(self.root)

    def call(self, method, path, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_lists_today_and_logging_through_the_api(self):
        secure = {"X-Recon": "1"}
        self.assertEqual(self.call("POST", "/api/lists", {"name": "Leeds"})[0], 403)
        status, made = self.call("POST", "/api/lists", {"name": "Leeds", "items": rows(), "query": {"near": ["Leeds"]}}, secure)
        self.assertEqual((status, made["name"], len(made["items"])), (201, "Leeds", 4))
        status, lists = self.call("GET", "/api/lists")
        self.assertEqual((status, lists[0]["businesses"]), (200, 4))
        status, today = self.call("GET", f"/api/today?list={made['id']}&count=2")
        self.assertEqual((status, [c["name"] for c in today]), (200, ["Glow Room", "Trade Co"]))
        status, logged = self.call("POST", "/api/contacts/g1/log", {"outcome": "interested", "note": "Demo Friday"}, secure)
        self.assertEqual((status, logged["status"], logged["note"]), (200, "interested", "Demo Friday"))
        status, body = self.call("POST", "/api/contacts/g1/log", {"outcome": "call back"}, secure)
        self.assertEqual((status, body["error"]), (400, "Pick a day to call back"))
        status, body = self.call("GET", "/api/calls/setup")
        self.assertEqual((status, body["configured"]), (200, False))
        status, body = self.call("POST", "/api/calls/start", {"business": "g1"}, secure)
        self.assertEqual(status, 400)
        self.assertIn("not been checked", body["error"])
        status, body = self.call("POST", "/api/screening", {"rows": [{"phone": "0113 111 1111", "result": "clear"}]}, secure)
        self.assertEqual((status, body["saved"]), (200, 1))
        status, body = self.call("POST", "/api/calls/start", {"business": "g1"}, secure)
        self.assertIn("not switched on", body["error"])
        status, body = self.call("POST", "/api/blocked", {"phone": "07700 900002", "reason": "asked"}, secure)
        self.assertEqual((status, body[0]["phone"]), (201, "+447700900002"))
        status, body = self.call("GET", "/api/contacts/g2")
        self.assertTrue(body["blocked"])
        status, niches = self.call("POST", "/api/niches", {"name": "Salons", "query": {"sector": ["beauty"]}}, secure)
        self.assertEqual((status, niches[0]["name"]), (201, "Salons"))
        status, body = self.call("DELETE", f"/api/lists/{made['id']}/items/g4", None, secure)
        self.assertEqual(status, 200)
        status, detail = self.call("GET", f"/api/lists/{made['id']}")
        self.assertEqual(len(detail["items"]), 3)
        status, body = self.call("DELETE", f"/api/lists/{made['id']}", None, secure)
        self.assertEqual((status, body["deleted"]), (200, made["id"]))
        self.assertEqual(self.call("GET", f"/api/lists/{made['id']}")[0], 404)
        self.assertEqual(self.call("POST", "/api/calls/webhook?key=x", {"event": "call.hangup"}, secure)[0], 200)


if __name__ == "__main__":
    unittest.main()
