#!/usr/bin/env python3
"""Blocklist controller for the edge DNS resolver (standard library only, so it runs on a stock python image).

Watches Blocklist objects (dns.vmd1.homelab/v1alpha1) in its own namespace, downloads each list, compiles it to a
sorted, de-duplicated list of domains, and serves the result over HTTP. The edge pods (dnsdist) pull the compiled
lists from here, so nothing heavy runs on the 1 GB edge nodes and no list has to fit in a 1 MiB Secret.

  GET /index.txt          name<TAB>sha256<TAB>entries, one line per ready list (503 until the first pass is done)
  GET /lists/<name>.txt.gz  the compiled list (gzip, one domain per line)
  GET /healthz, /readyz

Status is written back to each Blocklist (conditions, entries, contentHash, observedGeneration).
"""
import gzip
import hashlib
import json
import logging
import os
import re
import signal
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GROUP = "dns.vmd1.homelab"
VERSION = "v1alpha1"
PLURAL = "blocklists"
SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"

DATA_DIR = os.environ.get("DATA_DIR", "/data")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))
MAX_DOWNLOAD_BYTES = int(os.environ.get("MAX_DOWNLOAD_BYTES", str(64 * 1024 * 1024)))
FETCH_TIMEOUT = int(os.environ.get("FETCH_TIMEOUT", "60"))
RETRY_AFTER_FAILURE = int(os.environ.get("RETRY_AFTER_FAILURE", "600"))
DEFAULT_REFRESH = "24h"
DEFAULT_MAX_ENTRIES = 200000

NAME_RE = re.compile(r"^[a-z0-9]{1,24}$")
_LABEL = r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?"
HOST_RE = re.compile(rf"^(?=.{{1,253}}$){_LABEL}(?:\.{_LABEL})+$")
IP_RE = re.compile(r"^(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9a-f:]+:[0-9a-f:.]*)$")
IGNORE_HOSTS = {"localhost.localdomain", "local", "broadcasthost", "ip6-localhost", "ip6-loopback"}

log = logging.getLogger("blocklist-controller")


# ---------------------------------------------------------------- parsing

def parse_duration(text, default_seconds=86400):
    """'30m', '12h', '1d', '90s' or a bare number of seconds. Falls back to the default on garbage."""
    m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", str(text or ""))
    if not m:
        return default_seconds
    return max(60, int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)])


def _clean(name):
    name = name.strip().lower().rstrip(".")
    if name.startswith("*."):
        name = name[2:]
    name = name.lstrip(".")
    if not name or name in IGNORE_HOSTS or IP_RE.match(name) or not HOST_RE.match(name):
        return None
    return name


def parse_list(text, fmt):
    """Return the sorted unique domains of a list. fmt: 'hosts' ('XXX.XXX.XXX.XXX example.com', one or more names per
    line) or 'domains' (one domain per line, '*.' and leading dots stripped)."""
    out = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("!", ";")):
            continue
        parts = line.split()
        if fmt == "hosts":
            if len(parts) < 2 or not IP_RE.match(parts[0].lower()):
                continue
            names = parts[1:]
        else:
            names = parts[:1]
        for n in names:
            c = _clean(n)
            if c:
                out.add(c)
    return sorted(out)


def compile_list(domains):
    """gzip (mtime 0, so equal input gives equal bytes) and the sha256 of the plain text."""
    plain = ("\n".join(domains) + "\n").encode() if domains else b""
    return gzip.compress(plain, compresslevel=6, mtime=0), hashlib.sha256(plain).hexdigest()


# ---------------------------------------------------------------- download

class FetchError(Exception):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def fetch(url):
    if not url.lower().startswith(("https://", "http://")):
        raise FetchError("InvalidURL", f"unsupported URL scheme: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "vmd1-blocklist-controller/1"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT, context=ssl.create_default_context()) as resp:
            buf = bytearray()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > MAX_DOWNLOAD_BYTES:
                    raise FetchError("TooLarge", f"download exceeds {MAX_DOWNLOAD_BYTES} bytes")
            return buf.decode("utf-8", errors="replace")
    except FetchError:
        raise
    except urllib.error.HTTPError as e:
        raise FetchError("FetchFailed", f"HTTP {e.code} from {url}")
    except Exception as e:  # DNS, TLS, timeout, connection reset
        raise FetchError("FetchFailed", f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- Kubernetes (in-cluster, stdlib)

class Kube:
    def __init__(self):
        self.base = f"https://{os.environ['KUBERNETES_SERVICE_HOST']}:{os.environ.get('KUBERNETES_SERVICE_PORT', '443')}"
        self.ctx = ssl.create_default_context(cafile=f"{SA_DIR}/ca.crt")

    def _token(self):
        with open(f"{SA_DIR}/token") as f:  # re-read: projected tokens rotate
            return f.read().strip()

    def request(self, method, path, body=None, content_type="application/json"):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token()}", "Accept": "application/json", "Content-Type": content_type})
        with urllib.request.urlopen(req, timeout=30, context=self.ctx) as resp:
            return json.loads(resp.read() or b"{}")

    def list_blocklists(self, namespace):
        return self.request("GET", f"/apis/{GROUP}/{VERSION}/namespaces/{namespace}/{PLURAL}").get("items", [])

    def patch_status(self, namespace, name, status):
        self.request("PATCH", f"/apis/{GROUP}/{VERSION}/namespaces/{namespace}/{PLURAL}/{name}/status",
                     {"status": status}, "application/merge-patch+json")


# ---------------------------------------------------------------- state and reconcile

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class State:
    """What is on disk and in the index, plus the schedule. Single writer (the reconcile loop); readers (HTTP) take the lock."""

    def __init__(self, data_dir):
        self.dir = data_dir
        self.lock = threading.Lock()
        self.lists = {}          # name -> {"sha256", "entries", "size"}
        self.last_attempt = {}   # name -> monotonic time of the last fetch attempt
        self.last_ok = {}        # name -> bool
        self.ready = False
        os.makedirs(os.path.join(data_dir, "lists"), exist_ok=True)

    def path(self, name):
        return os.path.join(self.dir, "lists", f"{name}.txt.gz")

    def store(self, name, gz, sha, entries):
        tmp = self.path(name) + ".tmp"
        with open(tmp, "wb") as f:
            f.write(gz)
        os.replace(tmp, self.path(name))
        with self.lock:
            self.lists[name] = {"sha256": sha, "entries": entries, "size": len(gz)}

    def drop(self, name):
        with self.lock:
            self.lists.pop(name, None)
        self.last_attempt.pop(name, None)
        self.last_ok.pop(name, None)
        try:
            os.remove(self.path(name))
        except FileNotFoundError:
            pass

    def index_text(self):
        with self.lock:
            return "".join(f"{n}\t{v['sha256']}\t{v['entries']}\n" for n, v in sorted(self.lists.items()))


def is_due(bl, state, now):
    spec = bl.get("spec", {})
    name = bl["metadata"]["name"]
    if name not in state.lists and name not in state.last_attempt:
        # First sight since this process started. The data dir is an emptyDir, so even a suspended list is
        # fetched once here; suspend only stops the refreshes after that.
        return True
    if spec.get("suspend"):
        return False
    if bl.get("status", {}).get("observedGeneration") != bl["metadata"].get("generation"):
        return True
    wait = parse_duration(spec.get("refreshInterval", DEFAULT_REFRESH))
    if not state.last_ok.get(name, False):
        wait = min(wait, RETRY_AFTER_FAILURE)
    return now - state.last_attempt.get(name, 0) >= wait


def refresh(bl, state, fetcher=fetch):
    """Download and compile one Blocklist. Returns the status dict to write back."""
    spec = bl.get("spec", {})
    name = bl["metadata"]["name"]
    gen = bl["metadata"].get("generation")
    state.last_attempt[name] = time.monotonic()
    prev = bl.get("status", {})
    base = {"observedGeneration": gen, "lastAttemptTime": now_iso()}

    def failed(reason, message):
        state.last_ok[name] = False
        log.warning("blocklist %s: %s: %s", name, reason, message)
        cond = {"type": "Ready", "status": "False", "reason": reason, "message": message[:300],
                "lastTransitionTime": now_iso()}
        # a failed refresh keeps serving the previous compiled list, if there is one
        return {**base, "conditions": [cond]}

    if not NAME_RE.match(name):
        return failed("InvalidName", "name must match ^[a-z0-9]{1,24}$ (it is used in profile hostnames, where '-' separates lists)")
    try:
        text = fetcher(spec["url"])
    except FetchError as e:
        return failed(e.reason, str(e))
    except KeyError:
        return failed("InvalidSpec", "spec.url is required")

    domains = parse_list(text, spec.get("format", "hosts"))
    limit = int(spec.get("maxEntries") or DEFAULT_MAX_ENTRIES)
    if not domains:
        return failed("ParseFailed", f"no domains found (format={spec.get('format', 'hosts')})")
    if len(domains) > limit:
        return failed("TooLarge", f"{len(domains)} entries exceeds maxEntries={limit}; raise it only if the edge nodes have the memory")
    gz, sha = compile_list(domains)
    state.store(name, gz, sha, len(domains))
    state.last_ok[name] = True
    log.info("blocklist %s: %d entries, %d bytes gz, sha256 %s", name, len(domains), len(gz), sha[:12])
    changed = prev.get("contentHash") != sha
    old = (prev.get("conditions") or [{}])[0]
    # lastTransitionTime only moves when Ready flips, not on every refresh
    transition = old.get("lastTransitionTime", now_iso()) if old.get("status") == "True" else now_iso()
    cond = {"type": "Ready", "status": "True", "reason": "Compiled", "message": f"{len(domains)} domains",
            "lastTransitionTime": transition}
    return {**base, "conditions": [cond], "entries": len(domains), "contentHash": sha,
            "lastSuccessTime": now_iso(), **({"lastChangeTime": now_iso()} if changed else {})}


def reconcile_once(kube, namespace, state, fetcher=fetch):
    items = kube.list_blocklists(namespace)
    names = {bl["metadata"]["name"] for bl in items}
    for gone in [n for n in list(state.lists) if n not in names]:
        log.info("blocklist %s deleted; dropping its list", gone)
        state.drop(gone)
    now = time.monotonic()
    for bl in items:
        if not is_due(bl, state, now):
            continue
        status = refresh(bl, state, fetcher)
        try:
            kube.patch_status(namespace, bl["metadata"]["name"], status)
        except Exception as e:
            log.error("status update for %s failed: %s", bl["metadata"]["name"], e)
    state.ready = True  # every existing Blocklist has had its first attempt; failed ones serve nothing, others serve


# ---------------------------------------------------------------- HTTP

def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        server_version = "blocklist-controller"

        def log_message(self, fmt, *args):  # quiet: edge pods poll every minute
            pass

        def _send(self, code, body=b"", ctype="text/plain"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/healthz":
                return self._send(200, b"ok\n")
            if self.path == "/readyz":
                return self._send(200 if state.ready else 503, b"ok\n" if state.ready else b"not ready\n")
            if not state.ready:
                return self._send(503, b"not ready\n")
            if self.path == "/index.txt":
                return self._send(200, state.index_text().encode())
            m = re.fullmatch(r"/lists/([a-z0-9]{1,24})\.txt\.gz", self.path)
            if m and m.group(1) in state.lists:
                try:
                    with open(state.path(m.group(1)), "rb") as f:
                        return self._send(200, f.read(), "application/gzip")
                except FileNotFoundError:
                    pass
            return self._send(404, b"not found\n")

    return Handler


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    namespace = os.environ.get("NAMESPACE")
    if not namespace:
        with open(f"{SA_DIR}/namespace") as f:
            namespace = f.read().strip()
    state = State(DATA_DIR)
    kube = Kube()
    server = ThreadingHTTPServer(("XXX.XXX.XXX.XXX", LISTEN_PORT), make_handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    log.info("serving on :%d, watching %s/%s in %s every %ds", LISTEN_PORT, PLURAL, VERSION, namespace, POLL_INTERVAL)
    while not stop.is_set():
        try:
            reconcile_once(kube, namespace, state)
        except Exception:
            log.exception("reconcile failed")
        stop.wait(POLL_INTERVAL)
    server.shutdown()


if __name__ == "__main__":
    main()
