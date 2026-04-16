"""Inject an XLATE8-produced IPv4 ICMP frame through TWO FRR routers.

Runs inside the ipv8m-hostA container.  Uses the ipv8 package's
``XLATE8.v8_to_v4_packet`` to produce the wire bytes.
"""
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipv8 import IPv8Address, build_packet, PROTO_ICMP
from ipv8.packet import checksum16
from ipv8.xlate import XLATE8


def build_icmpv4_echo(identifier: int, sequence: int, payload: bytes) -> bytes:
    import struct
    header_no_cs = struct.pack("!BBHHH", 8, 0, 0, identifier, sequence)
    cs = checksum16(header_no_cs + payload)
    return struct.pack("!BBHHH", 8, 0, cs, identifier, sequence) + payload


def main() -> int:
    src_v4 = "198.20.1.10"
    dst_v4 = "198.20.2.10"
    src = IPv8Address.ipv4_compat(src_v4)
    dst = IPv8Address.ipv4_compat(dst_v4)

    icmpv4 = build_icmpv4_echo(0xD001, 11, b"two-hop-xlate")
    v8 = build_packet(
        src=src, dst=dst, payload=icmpv4, protocol=PROTO_ICMP, ttl=64,
    )
    print(f"IPv8: {v8.summary()}")
    xl = XLATE8(v4_to_v8={})
    v4_frame = xl.v8_to_v4_packet(v8)
    print(f"XLATE8 produced {len(v4_frame)}B IPv4 frame")

    send_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
    send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    recv_sock.settimeout(5)

    send_sock.sendto(v4_frame, (dst_v4, 0))
    try:
        data, peer = recv_sock.recvfrom(2048)
    except socket.timeout:
        print("NO REPLY (timeout)")
        return 2
    print(f"RX {len(data)}B from {peer[0]} — two FRR routers forwarded our XLATE8 packet.")
    return 0 if data[20] == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
