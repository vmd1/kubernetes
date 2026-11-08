import json
import os
import tempfile
import unittest

os.environ["API_KEY"] = "k"
import tsint_sync as t  # noqa: E402


def node(name, ip, kind="InternalIP"):
    return {"metadata": {"name": name}, "status": {"addresses": [{"type": kind, "address": ip}, {"type": "ExternalIP", "address": "XXX.XXX.XXX.XXX"}]}}


def svc(name, ip, hostname=None, cls="tailscale"):
    meta = {"name": name, "annotations": {"tailscale.com/hostname": hostname} if hostname else {}}
    return {"metadata": meta, "spec": {"loadBalancerClass": cls}, "status": {"loadBalancer": {"ingress": [{"hostname": "x.ts.net"}, {"ip": ip}]}}}


class TsIntTest(unittest.TestCase):
    def test_nodes_use_their_tailnet_internal_ip_lowercased(self):
        got = t.from_nodes([node("Hades-01", "XXX.XXX.XXX.XXX"), node("lan-box", "XXX.XXX.XXX.XXX"), node("x", "XXX.XXX.XXX.XXX", kind="ExternalIP")])
        self.assertEqual(got, {"hades-01": "XXX.XXX.XXX.XXX"})

    def test_only_tailscale_class_services_with_a_tailnet_ip_count(self):
        got = t.from_services([svc("lan-dns", "XXX.XXX.XXX.XXX", hostname="LAN-DNS"), svc("plain", "XXX.XXX.XXX.XXX", cls=None), svc("nolb", "XXX.XXX.XXX.XXX")])
        self.assertEqual(got, {"lan-dns": "XXX.XXX.XXX.XXX"})

    def test_cluster_wins_over_static_and_static_fills_gaps(self):
        rr = t.desired([node("zeus-01", "XXX.XXX.XXX.XXX")], [svc("lan-dns", "XXX.XXX.XXX.XXX")],
                       {"dev": {"zeus-01": "XXX.XXX.XXX.XXX", "uk-home-subnet-router": "XXX.XXX.XXX.XXX"}, "srv": {"k8s-api": "XXX.XXX.XXX.XXX"}})
        by = {r["name"]: r["records"][0]["content"] for r in rr if r["type"] == "A"}
        self.assertEqual(by, {
            "uk-home-subnet-router.dev.ts.int.vmd1.homelab.": "XXX.XXX.XXX.XXX",
            "zeus-01.dev.ts.int.vmd1.homelab.": "XXX.XXX.XXX.XXX",
            "k8s-api.srv.ts.int.vmd1.homelab.": "XXX.XXX.XXX.XXX",
            "lan-dns.srv.ts.int.vmd1.homelab.": "XXX.XXX.XXX.XXX"})
        self.assertEqual(rr[0]["type"], "NS")

    def test_inventory_adds_non_cluster_devices_and_the_cluster_still_wins(self):
        rr = t.desired([node("zeus-01", "XXX.XXX.XXX.XXX")], [], {"dev": {"x": "XXX.XXX.XXX.XXX"}},
                       {"dev": {"zeus-01": "XXX.XXX.XXX.XXX", "s23-fe": "XXX.XXX.XXX.XXX", "x": "XXX.XXX.XXX.XXX"}, "lab": {"zeus-01": "XXX.XXX.XXX.XXX"}, "srv": {"k8s-api": "XXX.XXX.XXX.XXX"}})
        by = {r["name"]: r["records"][0]["content"] for r in rr if r["type"] == "A"}
        self.assertEqual(by["zeus-01.dev.ts.int.vmd1.homelab."], "XXX.XXX.XXX.XXX")   # cluster > inventory
        self.assertEqual(by["x.dev.ts.int.vmd1.homelab."], "XXX.XXX.XXX.XXX")             # inventory > static
        self.assertEqual(by["s23-fe.dev.ts.int.vmd1.homelab."], "XXX.XXX.XXX.XXX")
        self.assertEqual(by["k8s-api.srv.ts.int.vmd1.homelab."], "XXX.XXX.XXX.XXX")
        self.assertEqual(by["zeus-01.lab.ts.int.vmd1.homelab."], "XXX.XXX.XXX.XXX")   # the lab group

    def test_missing_static_file_is_fine(self):
        self.assertEqual(t.load_static("/nonexistent/file.json"), {"dev": {}, "lab": {}, "srv": {}})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"dev": {"a": "XXX.XXX.XXX.XXX"}, "srv": {"b": "XXX.XXX.XXX.XXX"}}, f)
        self.assertEqual(t.load_static(f.name), {"dev": {"a": "XXX.XXX.XXX.XXX"}, "lab": {}, "srv": {"b": "XXX.XXX.XXX.XXX"}})
        os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
