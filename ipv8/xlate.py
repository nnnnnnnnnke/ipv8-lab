"""XLATE8 — IPv4 ↔ IPv8 translation (stateful at a router, stateless at edges).

The draft describes XLATE8 as the mechanism that lets an IPv4-only host talk
through an IPv8 core.  Since we have no real IPv4 stack here, we model the
translation as rewriting IPv4 headers into IPv8 headers (with ASN=0 for the
IPv4 side) and vice versa, preserving the payload.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .address import IPv8Address
from .packet import IPv8Packet, build_packet, checksum16


def ipv4_pack(
    src_ipv4: str,
    dst_ipv4: str,
    payload: bytes,
    protocol: int = 0,
    ttl: int = 64,
    identification: int = 0,
    tos: int = 0,
    flags: int = 0,
    fragment_offset: int = 0,
) -> bytes:
    """Build a minimal IPv4 packet (no options)."""
    def _a(s: str) -> int:
        parts = s.split(".")
        v = 0
        for p in parts:
            v = (v << 8) | int(p)
        return v

    total_length = 20 + len(payload)
    ver_ihl = (4 << 4) | 5
    flags_frag = ((flags & 0x7) << 13) | (fragment_offset & 0x1FFF)
    header = struct.pack(
        "!BBHHHBBHII",
        ver_ihl,
        tos & 0xFF,
        total_length,
        identification & 0xFFFF,
        flags_frag,
        ttl & 0xFF,
        protocol & 0xFF,
        0,  # checksum
        _a(src_ipv4),
        _a(dst_ipv4),
    )
    cs = checksum16(header)
    header = header[:10] + struct.pack("!H", cs) + header[12:]
    return header + payload


def ipv4_unpack(data: bytes):
    if len(data) < 20:
        raise ValueError("short IPv4")
    ver_ihl = data[0]
    ver = ver_ihl >> 4
    if ver != 4:
        raise ValueError(f"not IPv4: v={ver}")
    ihl = (ver_ihl & 0xF) * 4
    tos = data[1]
    total_length = struct.unpack("!H", data[2:4])[0]
    identification = struct.unpack("!H", data[4:6])[0]
    flags_frag = struct.unpack("!H", data[6:8])[0]
    flags = (flags_frag >> 13) & 0x7
    fragment_offset = flags_frag & 0x1FFF
    ttl = data[8]
    protocol = data[9]
    src = ".".join(str(b) for b in data[12:16])
    dst = ".".join(str(b) for b in data[16:20])
    payload = data[ihl:total_length]
    return {
        "src": src,
        "dst": dst,
        "ttl": ttl,
        "tos": tos,
        "identification": identification,
        "flags": flags,
        "fragment_offset": fragment_offset,
        "protocol": protocol,
        "payload": payload,
    }


@dataclass
class XLATE8:
    """Edge translator between IPv4 and IPv8.

    When an IPv4 packet enters the IPv8 core, the source is re-written as
    ASN=0 (IPv4-compat) and the destination is looked up in a static mapping
    of IPv4 → IPv8 addresses (playing the role of the DNS8/WHOIS8 step).
    """

    v4_to_v8: dict  # {ipv4_str: IPv8Address}
    local_asn: int = 0  # ASN applied when rewriting a "local IPv4" source

    def v4_to_v8_packet(self, v4: bytes) -> IPv8Packet:
        info = ipv4_unpack(v4)
        dst = self.v4_to_v8.get(info["dst"])
        if dst is None:
            raise KeyError(
                f"no IPv8 mapping for IPv4 destination {info['dst']}"
            )
        # Source: keep the original IPv4 as an IPv4-compat IPv8 if we do not
        # have a specific mapping for it, else use the mapping.
        src = self.v4_to_v8.get(info["src"])
        if src is None:
            src = IPv8Address.ipv4_compat(info["src"])
            if self.local_asn:
                src = IPv8Address.from_asn_and_ipv4(self.local_asn, info["src"])
        pkt = build_packet(
            src=src,
            dst=dst,
            payload=info["payload"],
            protocol=info["protocol"],
            ttl=info["ttl"],
            tos=info.get("tos", 0),
            identification=info.get("identification", 0),
        )
        # Carry IPv4 flags/frag inside the IPv8 header's equivalent fields so
        # they survive a v8→v4 round-trip.
        pkt.header.flags = info.get("flags", 0)
        pkt.header.fragment_offset = info.get("fragment_offset", 0)
        return pkt

    def v8_to_v4_packet(self, pkt: IPv8Packet, v4_meta: dict = None) -> bytes:
        """Reverse: only valid when src is IPv4-compat or mapped.

        ``v4_meta`` preserves fields that don't live in the IPv8 header but
        must survive for byte-equal round-tripping (flags/fragment offset).
        """
        src_ipv4 = pkt.header.src.ipv4_string
        dst_ipv4 = pkt.header.dst.ipv4_string
        meta = v4_meta or {}
        return ipv4_pack(
            src_ipv4=src_ipv4,
            dst_ipv4=dst_ipv4,
            payload=pkt.payload,
            protocol=pkt.header.protocol,
            ttl=pkt.header.ttl,
            identification=pkt.header.identification,
            tos=pkt.header.tos,
            flags=meta.get("flags", pkt.header.flags),
            fragment_offset=meta.get("fragment_offset", pkt.header.fragment_offset),
        )
