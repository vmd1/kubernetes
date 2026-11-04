"""Offline tests for controller.py (no cluster, no network). Run: python3 -m unittest test_controller -v"""
import gzip
import http.client
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
import controller as c  # noqa: E402

HOSTS = """# comment
XXX.XXX.XXX.XXX localhost
::1 localhost ip6-localhost
XXX.XXX.XXX.XXX XXX.XXX.XXX.XXX
XXX.XXX.XXX.XXX Ads.Example.com  # trailing comment
XXX.XXX.XXX.XXX tracker.example.net other.example.net
XXX.XXX.XXX.XXX ads.example.com
XXX.XXX.XXX.XXX broadcasthost
not-an-ip evil.example.org
XXX.XXX.XXX.XXX bad_domain_with_no_dot
"""


class FakeKube:
    def __init__(self, items):
        self.items, self.patches = items, []

    def list_blocklists(self, namespace):
        return self.items

    def patch_status(self, namespace, name, status):
        self.patches.append((name, status))


def bl(name, url="https://x/list", gen=1, status=None, **spec):
    return {"metadata": {"name": name, "generation": gen}, "spec": {"url": url, **spec}, "status": status or {}}


class Parsing(unittest.TestCase):
    def test_hosts_format(self):
        self.assertEqual(c.parse_list(HOSTS, "hosts"), ["ads.example.com", "other.example.net", "tracker.example.net"])

    def test_domains_format(self):
        text = "! adblock comment\n*.Wild.example.com\n.dot.example.com\nplain.example.org # c\n1.2.3.4\nlocalhost\n\n"
        self.assertEqual(c.parse_list(text, "domains"), ["dot.example.com", "plain.example.org", "wild.example.com"])

    def test_rejects_garbage(self):
        self.assertEqual(c.parse_list("XXX.XXX.XXX.XXX -bad.example.com\n0.0.0.0 a..b.com\n0.0.0.0 " + "a" * 64 + ".com\n", "hosts"), [])

    def test_durations(self):
        self.assertEqual(c.parse_duration("30m"), 1800)
        self.assertEqual(c.parse_duration("1d"), 86400)
        self.assertEqual(c.parse_duration("nonsense"), 86400)
        self.assertEqual(c.parse_duration("5s"), 60)  # floor

    def test_compile_is_deterministic(self):
        a = c.compile_list(["a.com", "b.com"])
        b = c.compile_list(["a.com", "b.com"])
        self.assertEqual(a, b)
        self.assertEqual(gzip.decompress(a[0]), b"a.com\nb.com\n")


class Reconcile(unittest.TestCase):
    def setUp(self):
        self.state = c.State(tempfile.mkdtemp())

    def run_once(self, items, fetcher):
        k = FakeKube(items)
        c.reconcile_once(k, "ns", self.state, fetcher)
        return k

    def test_compiles_and_reports(self):
        k = self.run_once([bl("ads")], lambda url: HOSTS)
        st = dict(k.patches)["ads"]
        self.assertEqual(st["entries"], 3)
        self.assertEqual(st["conditions"][0]["status"], "True")
        self.assertEqual(st["observedGeneration"], 1)
        self.assertIn("ads\t", self.state.index_text())
        self.assertTrue(self.state.ready)

    def test_failure_keeps_previous_list(self):
        self.run_once([bl("ads")], lambda url: HOSTS)
        before = self.state.index_text()

        def boom(url):
            raise c.FetchError("FetchFailed", "HTTP 500")
        # new generation forces a refresh
        k = self.run_once([bl("ads", gen=2, status={"observedGeneration": 1})], boom)
        self.assertEqual(dict(k.patches)["ads"]["conditions"][0]["reason"], "FetchFailed")
        self.assertEqual(self.state.index_text(), before)

    def test_too_large_is_rejected(self):
        k = self.run_once([bl("ads", maxEntries=2)], lambda url: HOSTS)
        st = dict(k.patches)["ads"]
        self.assertEqual(st["conditions"][0]["reason"], "TooLarge")
        self.assertEqual(self.state.index_text(), "")

    def test_empty_parse_fails(self):
        k = self.run_once([bl("ads")], lambda url: "# nothing\n")
        self.assertEqual(dict(k.patches)["ads"]["conditions"][0]["reason"], "ParseFailed")

    def test_invalid_name(self):
        k = self.run_once([bl("ads-trackers")], lambda url: HOSTS)
        self.assertEqual(dict(k.patches)["ads-trackers"]["conditions"][0]["reason"], "InvalidName")

    def test_deleted_blocklist_is_dropped(self):
        self.run_once([bl("ads"), bl("gambling")], lambda url: HOSTS)
        self.run_once([bl("ads", status={"observedGeneration": 1})], lambda url: HOSTS)
        self.assertNotIn("gambling", self.state.index_text())
        self.assertFalse(os.path.exists(self.state.path("gambling")))

    def test_not_due_until_interval(self):
        calls = []
        items = [bl("ads", refreshInterval="1d")]
        self.run_once(items, lambda url: calls.append(url) or HOSTS)
        items[0]["status"] = {"observedGeneration": 1}
        self.run_once(items, lambda url: calls.append(url) or HOSTS)
        self.assertEqual(len(calls), 1)

    def test_suspended_is_fetched_once_then_left_alone(self):
        calls = []
        items = [bl("ads", suspend=True)]
        self.run_once(items, lambda url: calls.append(url) or HOSTS)
        items[0]["status"] = {"observedGeneration": 1}
        items[0]["metadata"]["generation"] = 2  # edited while suspended: still no fetch
        self.run_once(items, lambda url: calls.append(url) or HOSTS)
        self.assertEqual(len(calls), 1)
        self.assertIn("ads\t", self.state.index_text())

    def test_failed_list_retries_before_interval(self):
        calls = []

        def boom(url):
            calls.append(url)
            raise c.FetchError("FetchFailed", "x")
        items = [bl("ads", refreshInterval="1d")]
        self.run_once(items, boom)
        self.state.last_attempt["ads"] -= c.RETRY_AFTER_FAILURE + 1
        items[0]["status"] = {"observedGeneration": 1}
        self.run_once(items, boom)
        self.assertEqual(len(calls), 2)

    def test_fetch_rejects_other_schemes(self):
        with self.assertRaises(c.FetchError):
            c.fetch("file:///etc/passwd")


class Http(unittest.TestCase):
    def setUp(self):
        self.state = c.State(tempfile.mkdtemp())
        self.server = ThreadingHTTPServer(("XXX.XXX.XXX.XXX", 0), c.make_handler(self.state))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def get(self, path):
        conn = http.client.HTTPConnection("XXX.XXX.XXX.XXX", self.server.server_port)
        conn.request("GET", path)
        r = conn.getresponse()
        return r.status, r.read()

    def test_not_ready_then_ready(self):
        self.assertEqual(self.get("/healthz")[0], 200)
        self.assertEqual(self.get("/readyz")[0], 503)
        self.assertEqual(self.get("/index.txt")[0], 503)
        gz, sha = c.compile_list(["a.com"])
        self.state.store("ads", gz, sha, 1)
        self.state.ready = True
        self.assertEqual(self.get("/readyz")[0], 200)
        self.assertEqual(self.get("/index.txt"), (200, f"ads\t{sha}\t1\n".encode()))
        status, body = self.get("/lists/ads.txt.gz")
        self.assertEqual((status, gzip.decompress(body)), (200, b"a.com\n"))

    def test_unknown_and_traversal(self):
        self.state.ready = True
        self.assertEqual(self.get("/lists/nope.txt.gz")[0], 404)
        self.assertEqual(self.get("/lists/../../etc/passwd")[0], 404)
        self.assertEqual(self.get("/lists/ADS.txt.gz")[0], 404)


if __name__ == "__main__":
    unittest.main()
