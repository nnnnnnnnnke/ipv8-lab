import unittest

from ipv8 import IPv8Address
from ipv8.address import BROADCAST


class TestAddress(unittest.TestCase):
    def test_string_roundtrip(self):
        a = IPv8Address.from_string("0.0.251.240.192.168.1.1")
        self.assertEqual(str(a), "0.0.251.240.192.168.1.1")
        self.assertEqual(a.to_bytes(), bytes.fromhex("0000fbf0c0a80101"))

    def test_draft_example_asn_encoding(self):
        # Draft: ASN 64496 encodes as 0.0.251.240
        a = IPv8Address.from_asn_and_ipv4(64496, "0.0.0.0")
        self.assertEqual(a.asn_octets, (0, 0, 251, 240))

    def test_from_bytes(self):
        data = bytes.fromhex("0000fbf0c0a80101")
        a = IPv8Address.from_bytes(data)
        self.assertEqual(a.asn, 64496)
        self.assertEqual(a.ipv4_string, "192.168.1.1")

    def test_ipv4_compat(self):
        a = IPv8Address.ipv4_compat("10.0.0.1")
        self.assertTrue(a.is_ipv4_compat())
        self.assertEqual(a.classify(), "ipv4-compat")
        self.assertFalse(a.is_routable())

    def test_broadcast(self):
        self.assertTrue(BROADCAST.is_broadcast())
        self.assertEqual(BROADCAST.classify(), "broadcast")

    def test_multicast_classes(self):
        all_routers = IPv8Address.from_string("255.255.0.0.224.0.0.1")
        self.assertTrue(all_routers.is_multicast())
        self.assertFalse(all_routers.is_broadcast())
        self.assertEqual(all_routers.classify(), "multicast")

    def test_internal_zone(self):
        a = IPv8Address.from_string("127.0.0.0.10.0.0.1")
        self.assertTrue(a.is_internal_zone())
        self.assertFalse(a.is_routable())

    def test_dmz(self):
        a = IPv8Address.from_string("127.127.0.0.10.0.0.1")
        self.assertTrue(a.is_dmz())

    def test_rine(self):
        a = IPv8Address.from_string("100.1.2.3.10.0.0.1")
        self.assertTrue(a.is_rine_peering())
        self.assertFalse(a.is_routable())

    def test_documentation(self):
        a = IPv8Address.from_string("0.0.255.253.10.0.0.1")
        self.assertTrue(a.is_documentation())

    def test_invalid_octets(self):
        with self.assertRaises(ValueError):
            IPv8Address.from_string("999.0.0.0.0.0.0.0")

    def test_wrong_part_count(self):
        with self.assertRaises(ValueError):
            IPv8Address.from_string("1.2.3.4")


if __name__ == "__main__":
    unittest.main()
