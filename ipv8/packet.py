"""IPv8 packet header encode/decode (40 bytes fixed, no options)."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

from .address import IPv8Address
from .constants import HEADER_LEN, IHL, IP_VERSION


def checksum16(data: bytes) -> int:
    """Standard 16-bit one's complement checksum (RFC 1071)."""
    if len(data) % 2:
        data = data + b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


@dataclass
class IPv8Header:
    src: IPv8Address
    dst: IPv8Address
    protocol: int = 0
    ttl: int = 64
    tos: int = 0
    identification: int = 0
    flags: int = 0  # 3 bits
    fragment_offset: int = 0  # 13 bits
    total_length: int = 0  # filled on pack()
    checksum: int = 0  # filled on pack()
    version: int = IP_VERSION
    ihl: int = IHL

    def _header_without_checksum(self, total_length: int) -> bytes:
        ver_ihl = ((self.version & 0xF) << 4) | (self.ihl & 0xF)
        flags_frag = ((self.flags & 0x7) << 13) | (self.fragment_offset & 0x1FFF)
        # Fixed part (12 bytes) + src(8) + dst(8) == 28; but spec uses 40B.
        # The draft shows the same layout as IPv4 plus 16 more bytes of address.
        # Field sizes (matching IPv4 control plane):
        #   ver/ihl   : 1
        #   tos       : 1
        #   total_len : 2
        #   id        : 2
        #   flags/frag: 2
        #   ttl       : 1
        #   proto     : 1
        #   checksum  : 2  (zeroed for calc)
        #   src       : 8
        #   dst       : 8
        # Total: 28 bytes.  Draft states "40 bytes" — we pad 12 bytes of
        # reserved zero options to match, since no optional extensions are
        # defined. This keeps IHL=10 consistent.
        fixed = struct.pack(
            "!BBHHHBBH",
            ver_ihl,
            self.tos & 0xFF,
            total_length & 0xFFFF,
            self.identification & 0xFFFF,
            flags_frag,
            self.ttl & 0xFF,
            self.protocol & 0xFF,
            0,  # checksum placeholder
        )
        return fixed + self.src.to_bytes() + self.dst.to_bytes() + b"\x00" * 12

    def pack(self, payload: bytes = b"") -> bytes:
        total_length = HEADER_LEN + len(payload)
        self.total_length = total_length
        raw = self._header_without_checksum(total_length)
        cs = checksum16(raw)
        self.checksum = cs
        # Re-insert checksum at offset 10..12
        packed = raw[:10] + struct.pack("!H", cs) + raw[12:]
        return packed + payload

    @classmethod
    def unpack(cls, data: bytes) -> "IPv8Packet":
        if len(data) < HEADER_LEN:
            raise ValueError(
                f"short packet: need at least {HEADER_LEN} bytes, got {len(data)}"
            )
        ver_ihl = data[0]
        version = (ver_ihl >> 4) & 0xF
        ihl = ver_ihl & 0xF
        if version != IP_VERSION:
            raise ValueError(f"not an IPv8 packet (version={version})")
        if ihl != IHL:
            raise ValueError(f"unsupported IHL: {ihl}")
        (tos, total_length, identification, flags_frag, ttl, protocol, checksum) = (
            struct.unpack("!BHHHBBH", data[1:12])
        )
        flags = (flags_frag >> 13) & 0x7
        fragment_offset = flags_frag & 0x1FFF
        src = IPv8Address.from_bytes(data[12:20])
        dst = IPv8Address.from_bytes(data[20:28])
        if total_length > len(data):
            raise ValueError(
                f"total_length {total_length} > buffer {len(data)}"
            )
        payload = data[HEADER_LEN:total_length]
        header = cls(
            src=src,
            dst=dst,
            protocol=protocol,
            ttl=ttl,
            tos=tos,
            identification=identification,
            flags=flags,
            fragment_offset=fragment_offset,
            total_length=total_length,
            checksum=checksum,
            version=version,
            ihl=ihl,
        )
        # Verify checksum over the EXACT received 40 header bytes (including
        # the reserved trailing 12 bytes), with only the two checksum bytes
        # zeroed.  Using the raw bytes here means any flip in the header —
        # even inside the reserved area — is caught.
        raw = bytearray(data[:HEADER_LEN])
        raw[10:12] = b"\x00\x00"
        computed = checksum16(bytes(raw))
        if computed != checksum:
            raise ValueError(
                f"bad header checksum: stored=0x{checksum:04x}, "
                f"computed=0x{computed:04x}"
            )
        return IPv8Packet(header=header, payload=payload)


@dataclass
class IPv8Packet:
    header: IPv8Header
    payload: bytes = b""

    def to_bytes(self) -> bytes:
        return self.header.pack(self.payload)

    @classmethod
    def from_bytes(cls, data: bytes) -> "IPv8Packet":
        return IPv8Header.unpack(data)

    def summary(self) -> str:
        h = self.header
        return (
            f"IPv8 v={h.version} ihl={h.ihl} proto={h.protocol} ttl={h.ttl} "
            f"len={h.total_length} src={h.src} dst={h.dst} "
            f"cs=0x{h.checksum:04x} payload={len(self.payload)}B"
        )

    def hexdump(self) -> str:
        data = self.to_bytes()
        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i : i + 16]
            hexpart = " ".join(f"{b:02x}" for b in chunk)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{i:04x}  {hexpart:<47s}  {asc}")
        return "\n".join(lines)


def build_packet(
    src: IPv8Address,
    dst: IPv8Address,
    payload: bytes = b"",
    protocol: int = 0,
    ttl: int = 64,
    tos: int = 0,
    identification: int = 0,
) -> IPv8Packet:
    header = IPv8Header(
        src=src,
        dst=dst,
        protocol=protocol,
        ttl=ttl,
        tos=tos,
        identification=identification,
    )
    pkt = IPv8Packet(header=header, payload=payload)
    # Trigger pack to fill total_length and checksum
    pkt.to_bytes()
    return pkt
