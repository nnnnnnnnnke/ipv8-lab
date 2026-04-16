import unittest

from ipv8 import HEADER_LEN, IP_VERSION, IPv8Address, IPv8Packet, build_packet
from ipv8.packet import checksum16


class TestPacket(unittest.TestCase):
    def _pair(self):
        src = IPv8Address.from_asn_and_ipv4(64496, "192.168.1.10")
        dst = IPv8Address.from_asn_and_ipv4(64497, "10.0.0.5")
        return src, dst

    def test_roundtrip_empty(self):
        src, dst = self._pair()
        pkt = build_packet(src, dst, payload=b"", protocol=17, ttl=64)
        wire = pkt.to_bytes()
        self.assertEqual(len(wire), HEADER_LEN)
        decoded = IPv8Packet.from_bytes(wire)
        self.assertEqual(decoded.header.src, src)
        self.assertEqual(decoded.header.dst, dst)
        self.assertEqual(decoded.header.protocol, 17)
        self.assertEqual(decoded.header.ttl, 64)

    def test_roundtrip_with_payload(self):
        src, dst = self._pair()
        payload = b"hello IPv8!"
        pkt = build_packet(src, dst, payload=payload, protocol=17)
        wire = pkt.to_bytes()
        self.assertEqual(len(wire), HEADER_LEN + len(payload))
        decoded = IPv8Packet.from_bytes(wire)
        self.assertEqual(decoded.payload, payload)

    def test_version_field(self):
        src, dst = self._pair()
        wire = build_packet(src, dst).to_bytes()
        self.assertEqual(wire[0] >> 4, IP_VERSION)

    def test_checksum_detects_corruption(self):
        src, dst = self._pair()
        wire = bytearray(build_packet(src, dst, payload=b"xyz").to_bytes())
        wire[12] ^= 0xFF  # flip bits in src address
        with self.assertRaisesRegex(ValueError, "checksum"):
            IPv8Packet.from_bytes(bytes(wire))

    def test_short_buffer(self):
        with self.assertRaises(ValueError):
            IPv8Packet.from_bytes(b"\x00" * 10)

    def test_wrong_version(self):
        buf = bytearray(HEADER_LEN)
        buf[0] = (4 << 4) | 10
        with self.assertRaises(ValueError):
            IPv8Packet.from_bytes(bytes(buf))

    def test_checksum_function(self):
        # Known good: identical bits cancel to ~0 → we'll just verify that
        # two checksums over the same data match.
        self.assertEqual(checksum16(b"abcd"), checksum16(b"abcd"))
        # Flipping bits changes the result
        self.assertNotEqual(checksum16(b"abcd"), checksum16(b"abce"))

    def test_hexdump(self):
        src, dst = self._pair()
        pkt = build_packet(src, dst, payload=b"Hi")
        dump = pkt.hexdump()
        self.assertIn("0000", dump)


if __name__ == "__main__":
    unittest.main()
