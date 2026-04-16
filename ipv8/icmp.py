"""Minimal ICMPv8 (echo request/reply only)."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .packet import checksum16

TYPE_ECHO_REQUEST = 128
TYPE_ECHO_REPLY = 129


@dataclass
class ICMPv8Message:
    icmp_type: int
    code: int
    identifier: int
    sequence: int
    data: bytes = b""

    def to_bytes(self) -> bytes:
        header = struct.pack(
            "!BBHHH",
            self.icmp_type & 0xFF,
            self.code & 0xFF,
            0,  # checksum placeholder
            self.identifier & 0xFFFF,
            self.sequence & 0xFFFF,
        )
        raw = header + self.data
        cs = checksum16(raw)
        return header[:2] + struct.pack("!H", cs) + header[4:] + self.data

    @classmethod
    def from_bytes(cls, buf: bytes) -> "ICMPv8Message":
        if len(buf) < 8:
            raise ValueError("icmp too short")
        t, c, cs, ident, seq = struct.unpack("!BBHHH", buf[:8])
        data = buf[8:]
        # verify checksum
        header_zero = struct.pack("!BBHHH", t, c, 0, ident, seq)
        expected = checksum16(header_zero + data)
        if expected != cs:
            raise ValueError(
                f"bad ICMPv8 checksum: stored=0x{cs:04x} computed=0x{expected:04x}"
            )
        return cls(t, c, ident, seq, data)


def echo_request(identifier: int, sequence: int, payload: bytes = b"hello") -> bytes:
    return ICMPv8Message(
        TYPE_ECHO_REQUEST, 0, identifier, sequence, payload
    ).to_bytes()


def echo_reply(identifier: int, sequence: int, payload: bytes = b"hello") -> bytes:
    return ICMPv8Message(
        TYPE_ECHO_REPLY, 0, identifier, sequence, payload
    ).to_bytes()
