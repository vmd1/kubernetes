import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["API_KEY"] = "k"
import loader  # noqa: E402


class FakePdns(BaseHTTPRequestHandler):
    zones = {}      # name -> {"rrsets": [...], "meta": {kind: [..]}}
    calls = []

    def log_message(self, *a):
        pass

    def _send(self, code, body=None):
        raw = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n)) if n else None

    def _route(self, method):
        assert self.headers["X-API-Key"] == "k"
        path = urllib.parse.unquote(self.path)
        FakePdns.calls.append((method, path))
        base = "/api/v1/servers/localhost/zones"
        if path == base and method == "POST":
            b = self._body()
            FakePdns.zones[b["name"]] = {"rrsets": b["rrsets"], "meta": {}}
            return self._send(201, {})
        rest = path[len(base) + 1:]
        name, _, tail = rest.partition("/")
        z = FakePdns.zones.get(name)
        if z is None:
            return self._send(404, {"error": "Could not find domain"})
        if tail == "" and method == "GET":
            return self._send(200, {"name": name, "rrsets": z["rrsets"]})
        if tail == "" and method == "PATCH":
            for r in self._body()["rrsets"]:
                z["rrsets"] = [x for x in z["rrsets"] if (x["name"], x["type"]) != (r["name"], r["type"])]
                if r["changetype"] == "REPLACE":
                    z["rrsets"].append({k: v for k, v in r.items() if k != "changetype"})
            return self._send(204)
        if tail.startswith("metadata/"):
            kind = tail.split("/", 1)[1]
            if method == "GET":
                return self._send(200, {"kind": kind, "metadata": z["meta"].get(kind, [])})
            z["meta"][kind] = self._body()["metadata"]
            return self._send(200, {})
        return self._send(500, {"error": f"unhandled {method} {path}"})

    def do_GET(self): self._route("GET")
    def do_POST(self): self._route("POST")
    def do_PUT(self): self._route("PUT")
    def do_PATCH(self): self._route("PATCH")


def rrset(name, type_, ttl, *contents):
    return {"name": name, "type": type_, "ttl": ttl, "records": [{"content": c, "disabled": False} for c in contents]}


def zone_doc(rrsets):
    return {"zone": "a.test.", "kind": "Master", "rrsets": rrsets}


class LoaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("XXX.XXX.XXX.XXX", 0), FakePdns)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        loader.API_URL = f"http://XXX.XXX.XXX.XXX:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        FakePdns.zones = {}
        FakePdns.calls = []

    def doc(self, rrsets, h="h1"):
        d = zone_doc(rrsets)
        d["_hash"] = h
        return d

    SOA = rrset("a.test.", "SOA", 300, "ns1.a.test. admin.a.test. 1 1800 600 1209600 60")
    A1 = rrset("www.a.test.", "A", 300, "XXX.XXX.XXX.XXX")

    def test_creates_a_missing_zone_with_soa_and_stores_the_hash(self):
        self.assertTrue(loader.sync_zone(self.doc([self.SOA, self.A1])))
        z = FakePdns.zones["a.test."]
        self.assertEqual({r["type"] for r in z["rrsets"]}, {"SOA", "A"})
        self.assertEqual(z["meta"][loader.HASH_KIND], ["h1"])
        self.assertFalse(any("notify" in p for _, p in FakePdns.calls))

    def test_an_unchanged_zone_sends_nothing(self):
        loader.sync_zone(self.doc([self.SOA, self.A1]))
        FakePdns.calls.clear()
        self.assertFalse(loader.sync_zone(self.doc([self.SOA, self.A1])))
        self.assertTrue(all(m == "GET" for m, _ in FakePdns.calls), FakePdns.calls)

    def test_a_changed_zone_replaces_new_and_deletes_removed_rrsets_but_never_touches_the_soa(self):
        loader.sync_zone(self.doc([self.SOA, self.A1]))
        FakePdns.zones["a.test."]["rrsets"][0]["records"][0]["content"] = "ns1.a.test. admin.a.test. 99 1800 600 1209600 60"
        A2 = rrset("mail.a.test.", "A", 300, "XXX.XXX.XXX.XXX")
        self.assertTrue(loader.sync_zone(self.doc([self.SOA, A2], h="h2")))
        z = FakePdns.zones["a.test."]
        self.assertEqual(sorted((r["name"], r["type"]) for r in z["rrsets"]), [("a.test.", "SOA"), ("mail.a.test.", "A")])
        soa = next(r for r in z["rrsets"] if r["type"] == "SOA")
        self.assertIn(" 99 ", soa["records"][0]["content"])   # the primary's serial survived
        self.assertEqual(z["meta"][loader.HASH_KIND], ["h2"])

    def test_load_desired_hashes_the_file_and_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as d:
            for name, body in (("a.test.rrsets.json", json.dumps(zone_doc([self.SOA]))), ("a.test.zone", "x"), ("named.conf", "y")):
                with open(os.path.join(d, name), "w") as f:
                    f.write(body)
            docs = loader.load_desired(d)
            self.assertEqual([x["zone"] for x in docs], ["a.test."])
            self.assertEqual(len(docs[0]["_hash"]), 64)


if __name__ == "__main__":
    unittest.main()
