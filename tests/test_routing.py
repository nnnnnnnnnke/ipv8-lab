import unittest

from ipv8 import IPv8Address, Route, TwoTierRoutingTable


class TestRouting(unittest.TestCase):
    def test_exact_asn_lookup(self):
        rt = TwoTierRoutingTable()
        rt.add(
            Route(
                asn_prefix=64496,
                host_prefix=0xC0A80100,  # 192.168.1.0
                host_prefix_len=24,
                next_hop=IPv8Address.from_string("0.0.251.240.192.168.1.1"),
                interface="eth0",
            )
        )
        found = rt.lookup(IPv8Address.from_asn_and_ipv4(64496, "192.168.1.50"))
        self.assertIsNotNone(found)
        self.assertEqual(found.interface, "eth0")

    def test_longest_prefix(self):
        rt = TwoTierRoutingTable()
        rt.add(
            Route(
                asn_prefix=64496,
                host_prefix=0x0A000000,  # 10.0.0.0/8
                host_prefix_len=8,
                next_hop=None,
                interface="ethA",
            )
        )
        rt.add(
            Route(
                asn_prefix=64496,
                host_prefix=0x0A0A0000,  # 10.10.0.0/16
                host_prefix_len=16,
                next_hop=None,
                interface="ethB",
            )
        )
        # Address 10.10.5.1 → should match /16, not /8
        found = rt.lookup(IPv8Address.from_asn_and_ipv4(64496, "10.10.5.1"))
        self.assertEqual(found.interface, "ethB")
        # Address 10.20.5.1 → only /8
        found = rt.lookup(IPv8Address.from_asn_and_ipv4(64496, "10.20.5.1"))
        self.assertEqual(found.interface, "ethA")

    def test_miss_returns_default(self):
        rt = TwoTierRoutingTable()
        default = Route(0, 0, 0, None, "eth-default")
        rt.set_default(default)
        found = rt.lookup(IPv8Address.from_asn_and_ipv4(65000, "1.2.3.4"))
        self.assertEqual(found.interface, "eth-default")

    def test_miss_no_default(self):
        rt = TwoTierRoutingTable()
        self.assertIsNone(rt.lookup(IPv8Address.from_asn_and_ipv4(1, "1.1.1.1")))


if __name__ == "__main__":
    unittest.main()
