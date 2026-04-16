"""Demo 3 — XLATE8: an IPv4 packet enters the IPv8 core and comes out IPv4.

This shows draft section "XLATE8" — translation at AS edge.  The inner
payload is preserved; only the IP header changes.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipv8 import IPv8Address
from ipv8.xlate import XLATE8, ipv4_pack, ipv4_unpack


def main() -> None:
    v4_dst = "10.0.0.5"
    v4_src = "192.168.1.10"
    v8_dst = IPv8Address.from_asn_and_ipv4(64497, v4_dst)

    xlate = XLATE8(v4_to_v8={v4_dst: v8_dst}, local_asn=64496)

    v4_packet = ipv4_pack(v4_src, v4_dst, b"secret-payload", protocol=17, ttl=64)
    print(f"IPv4 IN:  {len(v4_packet)}B  src={v4_src} dst={v4_dst}")

    v8_packet = xlate.v4_to_v8_packet(v4_packet)
    print(f"IPv8 MID: {v8_packet.summary()}")

    # Reverse at the far edge
    v4_out = xlate.v8_to_v4_packet(v8_packet)
    info = ipv4_unpack(v4_out)
    print(f"IPv4 OUT: {len(v4_out)}B  src={info['src']} dst={info['dst']}  payload={info['payload']!r}")

    assert info["payload"] == b"secret-payload"
    print("\npayload preserved end-to-end ✓")


if __name__ == "__main__":
    main()
