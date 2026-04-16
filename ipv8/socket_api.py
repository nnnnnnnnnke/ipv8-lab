"""sockaddr_in8 equivalent — pure-Python struct, not a kernel binding."""

from __future__ import annotations

from dataclasses import dataclass

from .address import IPv8Address
from .constants import AF_INET8


@dataclass
class SockAddrIn8:
    family: int = AF_INET8
    port: int = 0
    addr: IPv8Address = IPv8Address(0, 0)

    def __post_init__(self) -> None:
        if self.family != AF_INET8:
            raise ValueError(f"family must be AF_INET8 ({AF_INET8})")
        if not 0 <= self.port <= 0xFFFF:
            raise ValueError("port out of range")

    def __str__(self) -> str:
        return f"[{self.addr}]:{self.port}"
