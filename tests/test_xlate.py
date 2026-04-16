import unittest

from ipv8 import IPv8Address
from ipv8.xlate import XLATE8, ipv4_pack, ipv4_unpack


class TestXlate(unittest.TestCase):
    def test_ipv4_roundtrip(self):
        raw = ipv4_pack("10.0.0.1", "10.0.0.2", b"data", protocol=17, ttl=50)
        info = ipv4_unpack(raw)
        self.assertEqual(info["src"], "10.0.0.1")
        self.assertEqual(info["dst"], "10.0.0.2")
        self.assertEqual(info["protocol"], 17)
        self.assertEqual(info["payload"], b"data")

    def test_v4_to_v8_translation(self):
        tx = XLATE8(
            v4_to_v8={
                "10.0.0.2": IPv8Address.from_asn_and_ipv4(64497, "10.0.0.2"),
            }
        )
        raw = ipv4_pack("10.0.0.1", "10.0.0.2", b"hi", protocol=17)
        pkt = tx.v4_to_v8_packet(raw)
        self.assertEqual(pkt.header.dst.asn, 64497)
        self.assertEqual(pkt.header.dst.ipv4_string, "10.0.0.2")
        # Source had no mapping → becomes IPv4-compat
        self.assertEqual(pkt.header.src.asn, 0)
        self.assertEqual(pkt.header.src.ipv4_string, "10.0.0.1")
        self.assertEqual(pkt.payload, b"hi")

    def test_v4_to_v8_missing_mapping(self):
        tx = XLATE8(v4_to_v8={})
        raw = ipv4_pack("10.0.0.1", "10.0.0.2", b"", protocol=17)
        with self.assertRaises(KeyError):
            tx.v4_to_v8_packet(raw)


if __name__ == "__main__":
    unittest.main()
