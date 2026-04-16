"""Build an IPv8 packet, run XLATE8, and send the resulting IPv4 bytes
through a real FRR router, proving end-to-end wire compatibility.

Intended to be copied into the ipv8-hostA container and executed there.
The ``ipv8`` package is bundled alongside this script.
"""
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipv8 import IPv8Address, build_packet, PROTO_ICMP
from ipv8.icmp import ICMPv8Message
from ipv8.packet import checksum16
from ipv8.xlate import XLATE8


def build_icmpv4_echo(identifier: int, sequence: int, payload: bytes) -> bytes:
    # IPv4 ICMP echo (type=8)
    import struct
    header_no_cs = struct.pack("!BBHHH", 8, 0, 0, identifier, sequence)
    cs = checksum16(header_no_cs + payload)
    return struct.pack("!BBHHH", 8, 0, cs, identifier, sequence) + payload


def main() -> int:
    src_v4 = "198.19.1.10"
    dst_v4 = "198.19.2.10"

    # Build an IPv8 packet whose IPv4-compat addresses are identical to the
    # hostA/hostB IPv4 addresses; this is the way the draft says IPv4 should
    # be carried (ASN=0).
    src = IPv8Address.ipv4_compat(src_v4)
    dst = IPv8Address.ipv4_compat(dst_v4)
    icmpv4 = build_icmpv4_echo(0xC002, 9, b"xlate-through-frr")
    v8_pkt = build_packet(
        src=src, dst=dst, payload=icmpv4,
        protocol=PROTO_ICMP, ttl=64,
    )
    print(f"IPv8: {v8_pkt.summary()}")

    # Use XLATE8 to emit the IPv4 wire bytes we will actually transmit.
    xl = XLATE8(v4_to_v8={})  # reverse direction: IPv8 (ASN=0) → IPv4
    v4_frame = xl.v8_to_v4_packet(v8_pkt)
    print(f"XLATE8 produced {len(v4_frame)}B IPv4 frame")

    send_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
    send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    recv_sock.settimeout(3)

    send_sock.sendto(v4_frame, (dst_v4, 0))
    try:
        data, peer = recv_sock.recvfrom(2048)
    except socket.timeout:
        print("NO REPLY (timeout)")
        return 2
    print(f"RX {len(data)}B from {peer[0]} — FRR forwarded an XLATE8-produced packet.")
    return 0 if data[20] == 0 else 3  # icmp_type after 20B IPv4 header


if __name__ == "__main__":
    sys.exit(main())
