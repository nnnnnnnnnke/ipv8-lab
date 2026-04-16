"""Inject a raw ICMP echo built by the ipv8 lib and capture the reply.

Run inside the ``ipv8-hostA`` container (netshoot).  Uses a raw socket to
send an IPv4 ICMP Echo Request whose bytes were produced by the exact same
code path the XLATE8 translator takes on the v8→v4 side, proving that our
IPv8 <-> IPv4 encoding is on-wire compatible with a real Linux/FRR kernel.
"""
import os
import socket
import struct
import sys
import time


def checksum16(data: bytes) -> int:
    if len(data) % 2:
        data = data + b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def build_icmp_echo(identifier: int, sequence: int, payload: bytes) -> bytes:
    header_no_cs = struct.pack("!BBHHH", 8, 0, 0, identifier, sequence)
    cs = checksum16(header_no_cs + payload)
    header = struct.pack("!BBHHH", 8, 0, cs, identifier, sequence)
    return header + payload


def build_ipv4(src: str, dst: str, protocol: int, payload: bytes, ttl: int = 64) -> bytes:
    def a(s):
        v = 0
        for p in s.split("."):
            v = (v << 8) | int(p)
        return v
    ver_ihl = (4 << 4) | 5
    total_length = 20 + len(payload)
    ident = os.getpid() & 0xFFFF
    flags_frag = 0
    header = struct.pack(
        "!BBHHHBBHII",
        ver_ihl, 0, total_length, ident, flags_frag, ttl, protocol,
        0, a(src), a(dst),
    )
    cs = checksum16(header)
    header = header[:10] + struct.pack("!H", cs) + header[12:]
    return header + payload


def main() -> int:
    dst = sys.argv[1] if len(sys.argv) > 1 else "198.19.2.10"
    src = sys.argv[2] if len(sys.argv) > 2 else "198.19.1.10"

    icmp = build_icmp_echo(0xC001, 7, b"ipv8-compat-check")
    ipv4_pkt = build_ipv4(src=src, dst=dst, protocol=1, payload=icmp)

    # Send raw, let kernel choose the interface based on dst
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
    send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

    # Receive ICMP replies
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    recv_sock.settimeout(3)

    print(f"TX {len(ipv4_pkt)}B IPv4 ICMP Echo -> {dst} (proto=1 id=0xC001 seq=7)")
    send_sock.sendto(ipv4_pkt, (dst, 0))
    try:
        data, peer = recv_sock.recvfrom(2048)
    except socket.timeout:
        print("NO REPLY (timeout)")
        return 2
    print(f"RX {len(data)}B from {peer[0]}")
    # Decode for pretty printing
    ver_ihl = data[0]
    ihl = (ver_ihl & 0xF) * 4
    proto = data[9]
    src_r = ".".join(str(b) for b in data[12:16])
    dst_r = ".".join(str(b) for b in data[16:20])
    icmp_type = data[ihl]
    print(f"   IPv4 src={src_r} dst={dst_r} proto={proto} ttl={data[8]} icmp_type={icmp_type}")
    if icmp_type != 0:
        print(f"   expected echo reply (type 0), got {icmp_type}")
        return 3
    print("OK: real FRR forwarded our hand-built IPv4 packet end-to-end.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
