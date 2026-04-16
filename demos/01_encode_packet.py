"""Demo 1 — encode/decode a single IPv8 packet and show the wire format.

Run:   python3 demos/01_encode_packet.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipv8 import IPv8Address, IPv8Packet, build_packet, PROTO_UDP


def main() -> None:
    src = IPv8Address.from_asn_and_ipv4(64496, "192.168.1.10")
    dst = IPv8Address.from_asn_and_ipv4(64497, "10.0.0.5")

    print(f"src = {src}    ({src.classify()})   ASN={src.asn}  IPv4-part={src.ipv4_string}")
    print(f"dst = {dst}    ({dst.classify()})   ASN={dst.asn}  IPv4-part={dst.ipv4_string}")

    pkt = build_packet(
        src=src, dst=dst, payload=b"Hello, IPv8!", protocol=PROTO_UDP, ttl=64
    )
    wire = pkt.to_bytes()

    print()
    print("Summary: " + pkt.summary())
    print()
    print("Hex dump (40-byte header + 12-byte payload):")
    print(pkt.hexdump())

    print()
    print("Round-trip decode:")
    again = IPv8Packet.from_bytes(wire)
    print("  " + again.summary())
    assert again.to_bytes() == wire
    print("  roundtrip OK")


if __name__ == "__main__":
    main()
