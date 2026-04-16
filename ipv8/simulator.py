"""Userspace multi-AS IPv8 simulator.

Hosts and Routers are Python objects connected by named "links" (queues).
Every packet forwarding decision is logged, producing a trace you can read
exactly like tcpdump output.
"""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional, Tuple

from .address import IPv8Address
from .icmp import (
    ICMPv8Message,
    TYPE_ECHO_REPLY,
    TYPE_ECHO_REQUEST,
    echo_reply,
    echo_request,
)
from .packet import IPv8Packet, build_packet
from .routing import Route, TwoTierRoutingTable
from .constants import PROTO_ICMPV8


# --- Trace logging ----------------------------------------------------------
@dataclass
class TraceEvent:
    t: int  # logical time step
    node: str
    action: str  # "send", "recv", "forward", "drop"
    packet: IPv8Packet
    note: str = ""

    def format(self) -> str:
        h = self.packet.header
        return (
            f"t={self.t:03d} {self.node:<12s} {self.action:<7s} "
            f"{h.src} -> {h.dst} ttl={h.ttl} proto={h.protocol} "
            f"len={h.total_length} {self.note}"
        )


class Trace:
    def __init__(self) -> None:
        self.events: List[TraceEvent] = []
        self._clock = itertools.count()

    def log(self, node: str, action: str, packet: IPv8Packet, note: str = "") -> None:
        self.events.append(
            TraceEvent(next(self._clock), node, action, packet, note)
        )

    def dump(self) -> str:
        return "\n".join(e.format() for e in self.events)


# --- Links ------------------------------------------------------------------
class Link:
    """A bidirectional byte pipe between two interfaces."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.endpoints: Dict[str, "Node"] = {}
        self.queues: Dict[str, Deque[bytes]] = {}

    def attach(self, node: "Node", iface: str) -> None:
        key = f"{node.name}/{iface}"
        self.endpoints[key] = node
        self.queues[key] = deque()

    def deliver(self, sender_key: str, frame: bytes) -> List[Tuple[str, "Node", bytes]]:
        """Enqueue to everyone except sender. Returns delivered list."""
        delivered = []
        for key, node in self.endpoints.items():
            if key == sender_key:
                continue
            self.queues[key].append(frame)
            delivered.append((key, node, frame))
        return delivered


# --- Nodes ------------------------------------------------------------------
@dataclass
class Interface:
    name: str
    address: IPv8Address
    link: Optional[Link] = None
    admin_down: bool = False  # Set to True by the IOS CLI 'shutdown' command.


class Node:
    def __init__(self, name: str, trace: Trace) -> None:
        self.name = name
        self.trace = trace
        self.interfaces: Dict[str, Interface] = {}
        self.rtable = TwoTierRoutingTable()

    def add_interface(self, iface_name: str, address: IPv8Address, link: Link) -> None:
        iface = Interface(name=iface_name, address=address, link=link)
        self.interfaces[iface_name] = iface
        link.attach(self, iface_name)

    def _owns_address(self, addr: IPv8Address) -> bool:
        return any(i.address == addr for i in self.interfaces.values())

    def _send_on(self, iface_name: str, packet: IPv8Packet) -> None:
        iface = self.interfaces[iface_name]
        assert iface.link is not None
        if iface.admin_down:
            self.trace.log(
                self.name, "drop", packet,
                note=f"egress-admin-down ({iface_name})",
            )
            return
        key = f"{self.name}/{iface_name}"
        iface.link.deliver(key, packet.to_bytes())


class Host(Node):
    """End host. Has a default gateway per address tier per the draft's
    'even/odd gateways' model — here we just keep one gateway."""

    def __init__(self, name: str, address: IPv8Address, trace: Trace) -> None:
        super().__init__(name, trace)
        self.address = address
        self.gateway_iface: Optional[str] = None
        self.inbox: List[IPv8Packet] = []
        self.ping_replies: List[Tuple[int, int]] = []  # (ident, seq)

    def send(self, dst: IPv8Address, payload: bytes, protocol: int = 0) -> IPv8Packet:
        pkt = build_packet(
            src=self.address, dst=dst, payload=payload, protocol=protocol
        )
        self.trace.log(self.name, "send", pkt)
        iface_name = self.gateway_iface or next(iter(self.interfaces))
        self._send_on(iface_name, pkt)
        return pkt

    def ping(self, dst: IPv8Address, identifier: int = 1, sequence: int = 1) -> IPv8Packet:
        return self.send(
            dst, echo_request(identifier, sequence), protocol=PROTO_ICMPV8
        )

    def receive(self, frame: bytes) -> None:
        try:
            pkt = IPv8Packet.from_bytes(frame)
        except ValueError as e:
            self.trace.log(self.name, "drop", _stub_packet(), note=f"parse: {e}")
            return
        if not self._owns_address(pkt.header.dst) and not pkt.header.dst.is_broadcast():
            self.trace.log(self.name, "drop", pkt, note="not-for-us")
            return
        self.trace.log(self.name, "recv", pkt)
        self.inbox.append(pkt)
        if pkt.header.protocol == PROTO_ICMPV8:
            msg = ICMPv8Message.from_bytes(pkt.payload)
            if msg.icmp_type == TYPE_ECHO_REQUEST:
                reply = build_packet(
                    src=pkt.header.dst,
                    dst=pkt.header.src,
                    payload=echo_reply(msg.identifier, msg.sequence, msg.data),
                    protocol=PROTO_ICMPV8,
                )
                self.trace.log(self.name, "send", reply, note="echo-reply")
                iface_name = self.gateway_iface or next(iter(self.interfaces))
                self._send_on(iface_name, reply)
            elif msg.icmp_type == TYPE_ECHO_REPLY:
                self.ping_replies.append((msg.identifier, msg.sequence))


class Router(Node):
    """Layer-3 router with two-tier routing and TTL decrement.

    Routers also terminate ICMPv8 echo requests aimed at their own interface
    addresses, and can source their own echo requests for CLI ``ping8``.
    """

    def __init__(self, name: str, trace: Trace) -> None:
        super().__init__(name, trace)
        self.ping_replies: List[Tuple[int, int]] = []

    def forward_once(self, frame: bytes, incoming_iface: str) -> None:
        try:
            pkt = IPv8Packet.from_bytes(frame)
        except ValueError as e:
            self.trace.log(self.name, "drop", _stub_packet(), note=f"parse: {e}")
            return

        if self._owns_address(pkt.header.dst):
            # Terminal; handle ICMP echo locally so a router can be pinged.
            self.trace.log(self.name, "recv", pkt)
            if pkt.header.protocol == PROTO_ICMPV8:
                msg = ICMPv8Message.from_bytes(pkt.payload)
                if msg.icmp_type == TYPE_ECHO_REQUEST:
                    reply = build_packet(
                        src=pkt.header.dst,
                        dst=pkt.header.src,
                        payload=echo_reply(msg.identifier, msg.sequence, msg.data),
                        protocol=PROTO_ICMPV8,
                    )
                    self.trace.log(self.name, "send", reply, note="echo-reply")
                    # Route the reply back out of the appropriate interface.
                    route = self.rtable.lookup(pkt.header.src)
                    out_iface = route.interface if route else incoming_iface
                    self._send_on(out_iface, reply)
                elif msg.icmp_type == TYPE_ECHO_REPLY:
                    self.ping_replies.append((msg.identifier, msg.sequence))
            return

        if pkt.header.ttl <= 1:
            self.trace.log(self.name, "drop", pkt, note="ttl-exceeded")
            return

        route = self.rtable.lookup(pkt.header.dst)
        if route is None:
            self.trace.log(self.name, "drop", pkt, note="no-route")
            return

        out_iface = self.interfaces.get(route.interface)
        if out_iface is not None and out_iface.admin_down:
            self.trace.log(
                self.name, "drop", pkt,
                note=f"egress-admin-down ({route.interface})",
            )
            return

        # Decrement TTL and rebuild checksum by re-packing the packet
        pkt.header.ttl -= 1
        pkt = build_packet(
            src=pkt.header.src,
            dst=pkt.header.dst,
            payload=pkt.payload,
            protocol=pkt.header.protocol,
            ttl=pkt.header.ttl,
            tos=pkt.header.tos,
            identification=pkt.header.identification,
        )
        self.trace.log(
            self.name,
            "forward",
            pkt,
            note=f"via {route.next_hop or 'direct'} dev {route.interface}",
        )
        self._send_on(route.interface, pkt)


def _stub_packet() -> IPv8Packet:
    from .packet import IPv8Header

    return IPv8Packet(IPv8Header(IPv8Address(0, 0), IPv8Address(0, 0)))


# --- Network: steps the world one quantum at a time -------------------------
class Network:
    def __init__(self) -> None:
        self.trace = Trace()
        self.links: Dict[str, Link] = {}
        self.nodes: Dict[str, Node] = {}

    def link(self, name: str) -> Link:
        if name not in self.links:
            self.links[name] = Link(name)
        return self.links[name]

    def add_node(self, node: Node) -> None:
        self.nodes[node.name] = node
        node._net = self

    def step(self, max_steps: int = 100) -> None:
        """Deliver queued frames until the network is idle."""
        for _ in range(max_steps):
            any_delivered = False
            for link in self.links.values():
                for key in list(link.queues.keys()):
                    q = link.queues[key]
                    while q:
                        frame = q.popleft()
                        node = link.endpoints[key]
                        iface_name = key.split("/", 1)[1]
                        iface = node.interfaces.get(iface_name)
                        if iface is not None and iface.admin_down:
                            try:
                                pkt = IPv8Packet.from_bytes(frame)
                            except ValueError:
                                pkt = _stub_packet()
                            self.trace.log(
                                node.name, "drop", pkt,
                                note=f"ingress-admin-down ({iface_name})",
                            )
                            any_delivered = True
                            continue
                        if isinstance(node, Host):
                            node.receive(frame)
                        elif isinstance(node, Router):
                            node.forward_once(frame, iface_name)
                        any_delivered = True
            if not any_delivered:
                return
        raise RuntimeError("network did not converge (loop?)")
