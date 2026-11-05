#!/usr/bin/env python3
"""Keeps /live/restrictions.yaml equal to the mounted Secret, rewriting it IN PLACE.

wstunnel reloads its --restrict-config when the file is written, but not when a Kubernetes Secret volume updates (the
kubelet swaps a symlink, which the watcher never sees). So the pod mounts the Secret here, and this copies it onto a
file that wstunnel watches. A missing or empty Secret means "deny everything", never "allow everything". wstunnel
keeps its old config when a reload fails to parse, so a half-written file cannot open the gateway up.

  sync.py --once   copy once and exit (init container: the file exists before wstunnel starts)
  sync.py          copy now and then every INTERVAL seconds (sidecar)
"""
import os
import sys
import time

SRC = os.environ.get("SRC", "/src/restrictions.yaml")
DST = os.environ.get("DST", "/live/restrictions.yaml")
INTERVAL = float(os.environ.get("INTERVAL", "5"))
DENY_ALL = "restrictions: []\n"


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def sync(src=SRC, dst=DST):
    """Returns True when dst was rewritten."""
    want = read(src)
    if not want or not want.strip():
        want = DENY_ALL
    if read(dst) == want:
        return False
    with open(dst, "r+" if os.path.exists(dst) else "w") as f:  # same inode: what the watcher follows
        f.seek(0)
        f.write(want)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())
    return True


def main():
    once = "--once" in sys.argv
    while True:
        try:
            if sync():
                print("restrictions updated", flush=True)
        except OSError as e:
            print(f"sync failed: {e}", file=sys.stderr, flush=True)
            if once:
                sys.exit(1)
        if once:
            return
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
