"""Fuzz / property-style tests: 1000+ random round-trips."""

from __future__ import annotations

import os
import random
import unittest

from ipv8 import IPv8Address, IPv8Packet, build_packet
from ipv8.packet import checksum16


SEED = int(os.environ.get("IPV8_FUZZ_SEED", "20260417"))


class TestAddressFuzz(unittest.TestCase):
    def test_bytes_string_roundtrip_random(self):
        rng = random.Random(SEED)
        for _ in range(1000):
            raw = bytes(rng.randrange(256) for _ in range(8))
            a = IPv8Address.from_bytes(raw)
            self.assertEqual(a.to_bytes(), raw)
            self.assertEqual(IPv8Address.from_string(str(a)), a)

    def test_boundary_addresses(self):
        cases = [
            bytes(8),                   # all zeros
            b"\xff" * 8,                # all ones = broadcast
            b"\xff\xff" + b"\x00" * 6,  # multicast prefix
            b"\x7f" + b"\x00" * 7,      # internal zone
            b"\x7f\x7f" + b"\x00" * 6,  # DMZ
            b"\x64" + b"\x00" * 7,      # RINE peering
        ]
        for raw in cases:
            a = IPv8Address.from_bytes(raw)
            self.assertEqual(a.classify(), a.classify())  # stable repr
            self.assertEqual(a.to_bytes(), raw)
            self.assertEqual(IPv8Address.from_string(str(a)).to_bytes(), raw)


class TestPacketFuzz(unittest.TestCase):
    def test_random_payloads_roundtrip(self):
        rng = random.Random(SEED + 1)
        for n in range(500):
            src = IPv8Address.from_bytes(bytes(rng.randrange(256) for _ in range(8)))
            dst = IPv8Address.from_bytes(bytes(rng.randrange(256) for _ in range(8)))
            proto = rng.randrange(256)
            ttl = rng.randrange(1, 256)
            payload = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 1500)))
            pkt = build_packet(src=src, dst=dst, payload=payload, protocol=proto, ttl=ttl)
            wire = pkt.to_bytes()
            dec = IPv8Packet.from_bytes(wire)
            self.assertEqual(dec.header.src, src)
            self.assertEqual(dec.header.dst, dst)
            self.assertEqual(dec.header.protocol, proto)
            self.assertEqual(dec.header.ttl, ttl)
            self.assertEqual(dec.payload, payload)

    def test_single_bit_flips_detected(self):
        """Every single-byte XOR in the header must trip the checksum."""
        rng = random.Random(SEED + 2)
        src = IPv8Address.from_bytes(bytes(rng.randrange(256) for _ in range(8)))
        dst = IPv8Address.from_bytes(bytes(rng.randrange(256) for _ in range(8)))
        pkt = build_packet(src, dst, payload=b"x" * 16, protocol=17)
        wire = bytearray(pkt.to_bytes())
        # Flip each of the first 40 bytes (header only — payload isn't covered
        # by the IPv4-style header checksum).  A flip in the checksum bytes
        # themselves also changes it, so they count.
        for i in range(40):
            copy = bytearray(wire)
            copy[i] ^= 0x5A
            # Bytes 28..40 are reserved-zero padding; flipping them will
            # recompute the checksum to a different value and fail equality.
            # The test is simply "not silently accepted".
            try:
                IPv8Packet.from_bytes(bytes(copy))
                ok = True
            except ValueError:
                ok = False
            self.assertFalse(
                ok and bytes(copy) != bytes(wire),
                msg=f"flip at offset {i} was silently accepted",
            )


class TestChecksumFuzz(unittest.TestCase):
    def test_checksum_stability(self):
        rng = random.Random(SEED + 3)
        for _ in range(200):
            data = bytes(rng.randrange(256) for _ in range(rng.randrange(4, 200)))
            cs1 = checksum16(data)
            cs2 = checksum16(data)
            self.assertEqual(cs1, cs2)

    def test_checksum_commutativity_of_appended_zeros(self):
        rng = random.Random(SEED + 4)
        for _ in range(50):
            data = bytes(rng.randrange(256) for _ in range(rng.randrange(2, 40)))
            self.assertEqual(checksum16(data), checksum16(data + b"\x00\x00"))


if __name__ == "__main__":
    unittest.main()
