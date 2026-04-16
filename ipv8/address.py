"""IPv8 address (64-bit = 32-bit ASN prefix + 32-bit host).

Text form uses 8 dotted octets: "r.r.r.r.n.n.n.n".
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Tuple

from .constants import (
    BROADCAST_PREFIX,
    DMZ_PREFIX,
    DOCUMENTATION_PREFIX,
    INTERNAL_ZONE_PREFIX_FIRST,
    MCAST_PREFIX,
    RINE_PEERING_PREFIX_FIRST,
)


@dataclass(frozen=True)
class IPv8Address:
    """64-bit IPv8 address. ``asn`` and ``host`` are 32-bit unsigned ints."""

    asn: int
    host: int

    def __post_init__(self) -> None:
        if not 0 <= self.asn <= 0xFFFFFFFF:
            raise ValueError(f"asn out of range: {self.asn}")
        if not 0 <= self.host <= 0xFFFFFFFF:
            raise ValueError(f"host out of range: {self.host}")

    # --- Construction helpers -------------------------------------------------
    @classmethod
    def from_bytes(cls, data: bytes) -> "IPv8Address":
        if len(data) != 8:
            raise ValueError(f"IPv8 address must be 8 bytes, got {len(data)}")
        asn, host = struct.unpack("!II", data)
        return cls(asn, host)

    @classmethod
    def from_string(cls, text: str) -> "IPv8Address":
        parts = text.strip().split(".")
        if len(parts) != 8:
            raise ValueError(
                f"IPv8 address must have 8 dotted octets, got {len(parts)}: {text!r}"
            )
        octets = []
        for p in parts:
            v = int(p)
            if not 0 <= v <= 255:
                raise ValueError(f"octet out of range: {p}")
            octets.append(v)
        asn = (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]
        host = (octets[4] << 24) | (octets[5] << 16) | (octets[6] << 8) | octets[7]
        return cls(asn, host)

    @classmethod
    def from_asn_and_ipv4(cls, asn_number: int, ipv4: str) -> "IPv8Address":
        """Build an IPv8 address from an ASN integer and IPv4 string."""
        if not 0 <= asn_number <= 0xFFFFFFFF:
            raise ValueError("asn_number out of range")
        parts = ipv4.split(".")
        if len(parts) != 4:
            raise ValueError(f"bad IPv4: {ipv4}")
        host = 0
        for p in parts:
            v = int(p)
            if not 0 <= v <= 255:
                raise ValueError(f"bad IPv4 octet: {p}")
            host = (host << 8) | v
        return cls(asn_number, host)

    @classmethod
    def ipv4_compat(cls, ipv4: str) -> "IPv8Address":
        """IPv4 address embedded as IPv8 (ASN prefix = 0)."""
        return cls.from_asn_and_ipv4(0, ipv4)

    # --- Serialization --------------------------------------------------------
    def to_bytes(self) -> bytes:
        return struct.pack("!II", self.asn, self.host)

    def octets(self) -> Tuple[int, ...]:
        return (
            (self.asn >> 24) & 0xFF,
            (self.asn >> 16) & 0xFF,
            (self.asn >> 8) & 0xFF,
            self.asn & 0xFF,
            (self.host >> 24) & 0xFF,
            (self.host >> 16) & 0xFF,
            (self.host >> 8) & 0xFF,
            self.host & 0xFF,
        )

    def __str__(self) -> str:
        return ".".join(str(o) for o in self.octets())

    def __repr__(self) -> str:
        return f"IPv8Address('{self}')"

    # --- Classification -------------------------------------------------------
    @property
    def asn_octets(self) -> Tuple[int, int, int, int]:
        o = self.octets()
        return o[0], o[1], o[2], o[3]

    @property
    def host_octets(self) -> Tuple[int, int, int, int]:
        o = self.octets()
        return o[4], o[5], o[6], o[7]

    @property
    def ipv4_string(self) -> str:
        return ".".join(str(o) for o in self.host_octets)

    def is_ipv4_compat(self) -> bool:
        return self.asn == 0

    def is_broadcast(self) -> bool:
        return self.asn_octets == BROADCAST_PREFIX and self.host == 0xFFFFFFFF

    def is_multicast(self) -> bool:
        return self.asn_octets[:2] == MCAST_PREFIX and not self.is_broadcast()

    def is_internal_zone(self) -> bool:
        return self.asn_octets[0] == INTERNAL_ZONE_PREFIX_FIRST

    def is_dmz(self) -> bool:
        return self.asn_octets == DMZ_PREFIX

    def is_rine_peering(self) -> bool:
        return self.asn_octets[0] == RINE_PEERING_PREFIX_FIRST

    def is_documentation(self) -> bool:
        return self.asn_octets == DOCUMENTATION_PREFIX

    def is_routable(self) -> bool:
        """Globally routable per draft classification."""
        if self.is_broadcast() or self.is_multicast():
            return False
        if self.is_internal_zone() or self.is_rine_peering():
            return False
        if self.is_ipv4_compat():
            # routable only inside the IPv4 system
            return False
        return True

    def classify(self) -> str:
        if self.is_broadcast():
            return "broadcast"
        if self.is_multicast():
            return "multicast"
        if self.is_ipv4_compat():
            return "ipv4-compat"
        if self.is_dmz():
            return "dmz"
        if self.is_internal_zone():
            return "internal-zone"
        if self.is_rine_peering():
            return "rine-peering"
        if self.is_documentation():
            return "documentation"
        return "global-unicast"


BROADCAST = IPv8Address(0xFFFFFFFF, 0xFFFFFFFF)
