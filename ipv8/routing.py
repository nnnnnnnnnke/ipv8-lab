"""Two-tier IPv8 routing table (ASN tier + host tier)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .address import IPv8Address


@dataclass
class Route:
    """A routing table entry.

    ``asn_prefix`` is the 32-bit ASN prefix matched exactly (0 means any-ASN,
    i.e. IPv4-compat routing tier-2 only).  ``host_prefix``/``host_prefix_len``
    form an IPv4-style longest-prefix match on the host field.
    """

    asn_prefix: int
    host_prefix: int
    host_prefix_len: int  # 0..32
    next_hop: Optional[IPv8Address]
    interface: str
    metric: int = 0

    def host_matches(self, host: int) -> bool:
        if self.host_prefix_len == 0:
            return True
        mask = (0xFFFFFFFF << (32 - self.host_prefix_len)) & 0xFFFFFFFF
        return (host & mask) == (self.host_prefix & mask)

    def describe(self) -> str:
        from .address import IPv8Address as A
        nh = str(self.next_hop) if self.next_hop else "connected"
        host_ip = ".".join(
            str((self.host_prefix >> (24 - 8 * i)) & 0xFF) for i in range(4)
        )
        return (
            f"asn={self.asn_prefix} host={host_ip}/{self.host_prefix_len} "
            f"via {nh} dev {self.interface} metric {self.metric}"
        )


@dataclass
class TwoTierRoutingTable:
    """Tier-1 indexed by ASN; each tier-2 bucket is a longest-prefix list."""

    tier1: Dict[int, List[Route]] = field(default_factory=dict)
    default: Optional[Route] = None

    def add(self, route: Route) -> None:
        self.tier1.setdefault(route.asn_prefix, []).append(route)
        # Keep each bucket sorted by longest prefix first for predictable
        # lookup cost.
        self.tier1[route.asn_prefix].sort(key=lambda r: -r.host_prefix_len)

    def set_default(self, route: Route) -> None:
        self.default = route

    def lookup(self, dst: IPv8Address) -> Optional[Route]:
        # Tier 1: exact ASN match
        bucket = self.tier1.get(dst.asn)
        if bucket is not None:
            for r in bucket:
                if r.host_matches(dst.host):
                    return r
        # If the destination is IPv4-compat (ASN=0), the draft says tier-1 is
        # bypassed: we still walked the ASN=0 bucket above.
        return self.default

    def dump(self) -> str:
        lines = []
        for asn, routes in sorted(self.tier1.items()):
            lines.append(f"[ASN {asn}]")
            for r in routes:
                lines.append(f"  {r.describe()}")
        if self.default:
            lines.append(f"[default] {self.default.describe()}")
        return "\n".join(lines)
