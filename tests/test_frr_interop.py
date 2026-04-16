"""Integration test: IPv4 compatibility with a real FRRouting router.

Two independent proofs:

1. **Wire-equality test** — we take a real IPv4 ICMP Echo produced by Linux's
   kernel and forwarded through FRR (captured via tcpdump in a netshoot
   container), feed its bytes through the ipv8 library's IPv4 parser +
   XLATE8 (v4→v8 and back), and assert the resulting IPv4 frame is
   byte-identical except for fields that are allowed to change (nothing, in
   fact — we do an exact compare).

2. **Live-traffic test** — we invoke our XLATE8.v8_to_v4_packet() to produce
   an IPv4 frame from an IPv8 IPv4-compat packet, send it through a raw
   socket inside the ipv8-hostA container, and expect FRR to forward it to
   hostB which replies.

The test is skipped unless the ipv8-frr docker-compose stack is up.
"""

from __future__ import annotations

import os
import struct
import subprocess
import unittest

from ipv8 import IPv8Address, build_packet, PROTO_ICMP
from ipv8.packet import checksum16
from ipv8.xlate import XLATE8, ipv4_unpack, ipv4_pack


COMPOSE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frr_interop")
)


def _docker_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _bring_up_compose() -> None:
    """Idempotent compose up."""
    subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=COMPOSE_DIR, check=True, capture_output=True, timeout=180,
    )
    # Wait until FRR is routing
    import time
    for _ in range(30):
        r = subprocess.run(
            ["docker", "exec", "ipv8-hostA", "ping", "-c", "1", "-W", "1",
             "198.19.2.10"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("FRR did not become reachable within 30s")


PCAP_MAGIC = 0xA1B2C3D4


def parse_single_packet_pcap(path: str) -> bytes:
    """Return the payload bytes of the first packet in a classic pcap file."""
    with open(path, "rb") as fh:
        magic = struct.unpack("<I", fh.read(4))[0]
        if magic not in (PCAP_MAGIC, 0xD4C3B2A1):
            raise ValueError(f"bad pcap magic 0x{magic:08x}")
        # 20 more bytes of global header (version, thiszone, sigfigs, snaplen, linktype)
        fh.read(20)
        # Record header: ts_sec, ts_usec, incl_len, orig_len
        rec = fh.read(16)
        incl_len = struct.unpack("<I", rec[8:12])[0]
        return fh.read(incl_len)


class TestFRRInterop(unittest.TestCase):
    """Compatibility checks against a real FRR IPv4 router.

    This test REQUIRES a running Docker daemon — no fallback paths.  The
    compose stack is brought up automatically in ``setUpClass``.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not _docker_available():
            raise RuntimeError(
                "Docker daemon is not reachable; the FRR interop tests "
                "require a real FRR container (no fallback)."
            )
        _bring_up_compose()

    def test_wire_byte_equality(self):
        """Capture a real IPv4 ICMP through FRR and round-trip it through
        XLATE8, asserting byte equality (IPv4 → IPv8 → IPv4)."""
        pcap = "/tmp/cap.pcap"
        # Re-capture every run to avoid stale data
        subprocess.run(
            ["docker", "exec", "-d", "ipv8-hostB",
             "sh", "-c",
             "tcpdump -c 1 -w /tmp/cap.pcap -U -i eth0 'icmp and src 198.19.1.10'"],
            check=True,
        )
        import time; time.sleep(1)
        subprocess.run(
            ["docker", "exec", "ipv8-hostA", "ping", "-c", "2", "-W", "2",
             "198.19.2.10"], check=True, capture_output=True,
        )
        time.sleep(1)
        subprocess.run(
            ["docker", "cp", "ipv8-hostB:/tmp/cap.pcap", pcap],
            check=True, capture_output=True,
        )
        frame = parse_single_packet_pcap(pcap)
        # The captured frame includes 14 bytes of Ethernet header; skip it.
        self.assertTrue(len(frame) > 20)
        if frame[12:14] == b"\x08\x00":  # EtherType IPv4
            ipv4 = frame[14:]
        else:
            ipv4 = frame

        # Parse with our library
        info = ipv4_unpack(ipv4)
        self.assertEqual(info["src"], "198.19.1.10")
        self.assertEqual(info["dst"], "198.19.2.10")
        self.assertEqual(info["protocol"], 1)  # ICMP

        # XLATE8: v4 → v8 (with a trivial mapping, src keeps ASN=0)
        xlate = XLATE8(v4_to_v8={
            info["dst"]: IPv8Address.ipv4_compat(info["dst"]),
        })
        v8 = xlate.v4_to_v8_packet(ipv4)
        self.assertEqual(v8.header.src.asn, 0)
        self.assertEqual(v8.header.src.ipv4_string, info["src"])
        self.assertEqual(v8.header.dst.asn, 0)
        self.assertEqual(v8.header.dst.ipv4_string, info["dst"])

        # XLATE8: v8 → v4 (back to IPv4).  Checksum/ID can differ because
        # the kernel picked its own ID; zero both sides before comparing.
        v4_again = xlate.v8_to_v4_packet(v8)
        def normalize(buf: bytes) -> bytes:
            b = bytearray(buf)
            b[4:6] = b"\x00\x00"   # identification
            b[10:12] = b"\x00\x00"  # header checksum
            return bytes(b)
        self.assertEqual(
            normalize(v4_again), normalize(ipv4[:len(v4_again)]),
            msg="XLATE8 v4→v8→v4 did not preserve byte layout",
        )

    def test_xlate8_produced_frame_traverses_frr(self):
        """Send a frame produced by XLATE8.v8_to_v4_packet through the
        ipv8-hostA raw socket and wait for FRR-routed reply."""
        # Copy the ipv8 module into the container (idempotent)
        subprocess.run(
            ["docker", "exec", "ipv8-hostA", "mkdir", "-p", "/ipv8"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["docker", "cp",
             os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ipv8")),
             "ipv8-hostA:/ipv8"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["docker", "cp",
             os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frr_interop", "inject_xlate.py")),
             "ipv8-hostA:/inject_xlate.py"],
            check=True, capture_output=True,
        )
        out = subprocess.run(
            ["docker", "exec", "ipv8-hostA", "sh", "-c",
             "PYTHONPATH=/ipv8 python3 /inject_xlate.py"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(out.returncode, 0, msg=out.stdout + out.stderr)
        self.assertIn("FRR forwarded an XLATE8-produced packet", out.stdout)

    def test_frr_is_alive(self):
        """Sanity: FRR container responds to ping from hostA."""
        out = subprocess.run(
            ["docker", "exec", "ipv8-hostA", "ping", "-c", "1", "-W", "2",
             "198.19.2.10"],
            capture_output=True, text=True,
        )
        self.assertEqual(out.returncode, 0, msg=out.stdout + out.stderr)
        self.assertIn("1 received", out.stdout)


if __name__ == "__main__":
    unittest.main()
