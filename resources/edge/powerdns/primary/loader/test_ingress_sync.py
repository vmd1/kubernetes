import json
import os
import unittest

os.environ["API_KEY"] = "k"
import ingress_sync as s  # noqa: E402

# Exactly what the old operator wrote into geoip-zones.yaml for these nodes (copied from the live ConfigMap, IPs replaced
# with documentation addresses).
NODES = [
    {"name": "ares-01", "zone": "in-mumbai-cloud", "ip": "XXX.XXX.XXX.XXX"},
    {"name": "ares-02", "zone": "in-mumbai-cloud", "ip": "XXX.XXX.XXX.XXX"},
    {"name": "hades-01", "zone": "uk-home", "ip": "XXX.XXX.XXX.XXX"},
    {"name": "hades-02", "zone": "uk-home", "ip": "XXX.XXX.XXX.XXX"},
    {"name": "hera-01", "zone": "fr-marseille-cloud", "ip": "XXX.XXX.XXX.XXX"},
]


class BuildTest(unittest.TestCase):
    def by(self, rr):
        return {(r["name"], r["type"]): r for r in rr}

    def test_apex_is_cloud_group_then_home_backups_in_the_old_operators_exact_form(self):
        rr = self.by(s.build_rrsets(NODES)[0])
        lua = rr[("ingress.vmd1.homelab.", "LUA")]["records"][0]["content"]
        self.assertEqual(lua, "A \"ifurlup('https://vmd1.homelab/health', { {'XXX.XXX.XXX.XXX', 'XXX.XXX.XXX.XXX', 'XXX.XXX.XXX.XXX'}, {'XXX.XXX.XXX.XXX', 'XXX.XXX.XXX.XXX'} }, {timeout=3, selector='pickclosest'})\"")

    def test_zone_rrsets_and_node_records(self):
        rr = self.by(s.build_rrsets(NODES)[0])
        self.assertEqual(rr[("uk-home.ingress.vmd1.homelab.", "LUA")]["records"][0]["content"],
                         "A \"ifurlup('https://vmd1.homelab/health', {'XXX.XXX.XXX.XXX', 'XXX.XXX.XXX.XXX'}, {timeout=3, selector='pickclosest'})\"")
        self.assertEqual(rr[("ares-02.in-mumbai-cloud.ingress.vmd1.homelab.", "A")]["records"][0]["content"], "XXX.XXX.XXX.XXX")
        self.assertEqual([r["content"] for r in rr[("ingress.vmd1.homelab.", "NS")]["records"]], ["ns1.vmd1.homelab.", "ns2.vmd1.homelab.", "ns3.vmd1.homelab.", "ns4.vmd1.homelab."])
        self.assertTrue(all(r["ttl"] == 60 for r in rr.values()))

    def test_hash_ignores_node_order_and_changes_with_content(self):
        a = s.build_rrsets(NODES)[1]
        self.assertEqual(a, s.build_rrsets(list(reversed(NODES)))[1])
        self.assertNotEqual(a, s.build_rrsets(NODES[:-1])[1])


if __name__ == "__main__":
    unittest.main()
