import unittest

import tailnet_inventory as t


def dev(name, ip, tags=None, v6="fd7a::1"):
    return {"name": f"{name}.tail.ts.net", "addresses": [ip, v6], "tags": tags}


class BuildTest(unittest.TestCase):
    def test_devices_skip_operator_proxies_and_use_the_magicdns_label(self):
        inv = t.build([dev("hades-01", "XXX.XXX.XXX.XXX", ["tag:k3s"]), dev("uk-home", "XXX.XXX.XXX.XXX", ["tag:k8s-operator"]),
                       dev("k8s-api-0", "XXX.XXX.XXX.XXX", ["tag:k8s-apiserver"]), dev("km-laptop", "XXX.XXX.XXX.XXX"),
                       {"name": "Admin’s MacBook.tail.ts.net", "addresses": ["XXX.XXX.XXX.XXX"]}], [])
        self.assertEqual(inv["dev"], {"hades-01": "XXX.XXX.XXX.XXX", "km-laptop": "XXX.XXX.XXX.XXX", "admin-s-macbook": "XXX.XXX.XXX.XXX"})

    def test_lab_is_the_k3s_tagged_devices(self):
        inv = t.build([dev("hades-01", "XXX.XXX.XXX.XXX", ["tag:k3s"]), dev("km-laptop", "XXX.XXX.XXX.XXX"), dev("srv1", "XXX.XXX.XXX.XXX", ["tag:servers"])], [])
        self.assertEqual(inv["lab"], {"hades-01": "XXX.XXX.XXX.XXX"})
        self.assertIn("hades-01", inv["dev"])   # still under dev as well

    def test_services_drop_the_svc_prefix_and_take_the_ipv4(self):
        inv = t.build([dev("a", "XXX.XXX.XXX.XXX")], [{"name": "svc:k8s-api", "addrs": ["fd7a::1f3a", "XXX.XXX.XXX.XXX"]}])
        self.assertEqual(inv["srv"], {"k8s-api": "XXX.XXX.XXX.XXX"})

    def test_duplicate_labels_get_a_suffix_and_devices_without_an_ipv4_are_skipped(self):
        inv = t.build([dev("phone", "XXX.XXX.XXX.XXX"), dev("phone", "XXX.XXX.XXX.XXX"), {"name": "v6only.t.ts.net", "addresses": ["fd7a::9"]}], [])
        self.assertEqual(inv["dev"], {"phone": "XXX.XXX.XXX.XXX", "phone-2": "XXX.XXX.XXX.XXX"})


if __name__ == "__main__":
    unittest.main()
