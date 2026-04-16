"""Shared helpers for building IPv8 simulator topologies in tests."""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from ipv8 import Host, IOSCLI, IPv8Address, Network, Route, Router


def addr(asn: int, v4: str) -> IPv8Address:
    return IPv8Address.from_asn_and_ipv4(asn, v4)


def asn_str(asn: int) -> str:
    return ".".join(str((asn >> (24 - 8 * i)) & 0xFF) for i in range(4))


class RouterBuilder:
    """Convenience to wire up routers quickly using the simulator directly."""

    def __init__(self, net: Network) -> None:
        self.net = net
        self.routers: Dict[str, Router] = {}
        self.hosts: Dict[str, Host] = {}

    def router(self, name: str) -> Router:
        r = Router(name, self.net.trace)
        self.net.add_node(r)
        self.routers[name] = r
        return r

    def host(self, name: str, address: IPv8Address, link) -> Host:
        h = Host(name, address, self.net.trace)
        h.add_interface("eth0", address, link)
        h.gateway_iface = "eth0"
        self.net.add_node(h)
        self.hosts[name] = h
        return h

    def attach(self, router: Router, iface: str, address: IPv8Address, link) -> None:
        router.add_interface(iface, address, link)

    def add_static(
        self,
        router: Router,
        target_asn: int,
        next_hop: IPv8Address,
        out_iface: str,
        host_prefix: int = 0,
        host_prefix_len: int = 0,
    ) -> None:
        router.rtable.add(
            Route(
                asn_prefix=target_asn,
                host_prefix=host_prefix,
                host_prefix_len=host_prefix_len,
                next_hop=next_hop,
                interface=out_iface,
            )
        )

    def add_connected(
        self,
        router: Router,
        asn: int,
        host_prefix: int,
        host_prefix_len: int,
        iface: str,
    ) -> None:
        router.rtable.add(
            Route(
                asn_prefix=asn,
                host_prefix=host_prefix,
                host_prefix_len=host_prefix_len,
                next_hop=None,
                interface=iface,
            )
        )
