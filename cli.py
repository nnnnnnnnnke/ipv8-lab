"""ipv8-lab — interactive IPv8 sandbox.

Launch with:  python3 cli.py
Type `help` for commands.  `quit` to exit.
"""
from __future__ import annotations

import shlex
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipv8 import (
    Host,
    IPv8Address,
    IPv8Packet,
    Network,
    Route,
    Router,
    build_packet,
    echo_request,
    PROTO_ICMPV8,
    PROTO_UDP,
)


HELP = """\
Commands:
  addr <a.b.c.d.e.f.g.h>           show classification of an address
  encode <src> <dst> [payload]     build a packet and hex-dump it
  decode <hex>                     decode a hex-encoded packet
  topo demo                        build the sample 2-AS topology
  hosts                            list hosts and their addresses
  routes <router>                  show router's routing table
  ping <hostA> <hostB> [id] [seq]  ICMPv8 echo between two sim hosts
  trace                            show the current packet trace
  reset                            clear the simulator state
  help                             show this message
  quit                             exit
"""


class Shell:
    def __init__(self) -> None:
        self.net = None
        self.nodes = {}

    def _build_demo(self) -> None:
        net = Network()
        linkA = net.link("linkA")
        linkCore = net.link("linkCore")
        linkB = net.link("linkB")
        addr_A = IPv8Address.from_asn_and_ipv4(64496, "192.168.1.10")
        addr_B = IPv8Address.from_asn_and_ipv4(64497, "10.0.0.5")
        hA = Host("hostA", addr_A, net.trace)
        hA.add_interface("eth0", addr_A, linkA); hA.gateway_iface = "eth0"
        hB = Host("hostB", addr_B, net.trace)
        hB.add_interface("eth0", addr_B, linkB); hB.gateway_iface = "eth0"
        addr_R1a = IPv8Address.from_asn_and_ipv4(64496, "192.168.1.1")
        addr_R1c = IPv8Address.from_asn_and_ipv4(64496, "222.0.0.1")
        addr_R2c = IPv8Address.from_asn_and_ipv4(64497, "222.0.0.2")
        addr_R2b = IPv8Address.from_asn_and_ipv4(64497, "10.0.0.1")
        R1 = Router("R1", net.trace)
        R1.add_interface("ethA", addr_R1a, linkA)
        R1.add_interface("ethCore", addr_R1c, linkCore)
        R1.rtable.add(Route(64496, 0xC0A80100, 24, None, "ethA"))
        R1.rtable.add(Route(64497, 0, 0, addr_R2c, "ethCore"))
        R2 = Router("R2", net.trace)
        R2.add_interface("ethCore", addr_R2c, linkCore)
        R2.add_interface("ethB", addr_R2b, linkB)
        R2.rtable.add(Route(64497, 0x0A000000, 8, None, "ethB"))
        R2.rtable.add(Route(64496, 0, 0, addr_R1c, "ethCore"))
        for n in (hA, hB, R1, R2):
            net.add_node(n)
        self.net = net
        self.nodes = {n.name: n for n in (hA, hB, R1, R2)}
        print("Built 2-AS topology:  hostA -- R1 == R2 -- hostB")

    def cmd_addr(self, args):
        a = IPv8Address.from_string(args[0])
        print(f"  text       : {a}")
        print(f"  bytes      : {a.to_bytes().hex()}")
        print(f"  asn (r.r.r.r): {a.asn} ({'.'.join(str(o) for o in a.asn_octets)})")
        print(f"  host (n.n.n.n): {a.ipv4_string}")
        print(f"  classify   : {a.classify()}")
        print(f"  routable?  : {a.is_routable()}")

    def cmd_encode(self, args):
        src = IPv8Address.from_string(args[0])
        dst = IPv8Address.from_string(args[1])
        payload = args[2].encode() if len(args) > 2 else b""
        pkt = build_packet(src=src, dst=dst, payload=payload, protocol=PROTO_UDP)
        print(pkt.summary())
        print(pkt.hexdump())
        print(f"wire: {pkt.to_bytes().hex()}")

    def cmd_decode(self, args):
        pkt = IPv8Packet.from_bytes(bytes.fromhex(args[0]))
        print(pkt.summary())
        print(f"payload: {pkt.payload!r}")

    def cmd_topo(self, args):
        if args and args[0] == "demo":
            self._build_demo()
        else:
            print("usage: topo demo")

    def cmd_hosts(self, args):
        for name, node in self.nodes.items():
            kind = type(node).__name__
            ifaces = ", ".join(f"{i}={iface.address}" for i, iface in node.interfaces.items())
            print(f"  {name:<8s} {kind:<8s}  {ifaces}")

    def cmd_routes(self, args):
        node = self.nodes.get(args[0])
        if not isinstance(node, Router):
            print(f"not a router: {args[0]}"); return
        print(node.rtable.dump())

    def cmd_ping(self, args):
        a = self.nodes.get(args[0]); b = self.nodes.get(args[1])
        if not isinstance(a, Host) or not isinstance(b, Host):
            print("both arguments must be Host names"); return
        ident = int(args[2]) if len(args) > 2 else 1
        seq = int(args[3]) if len(args) > 3 else 1
        a.ping(b.address, identifier=ident, sequence=seq)
        self.net.step()
        got = (ident, seq) in a.ping_replies
        print(f"{a.name} → {b.name}: {'reply received' if got else 'no reply'} (id={ident} seq={seq})")

    def cmd_trace(self, args):
        if self.net is None:
            print("no topology loaded"); return
        print(self.net.trace.dump())

    def cmd_reset(self, args):
        self.net = None
        self.nodes = {}
        print("cleared.")

    def run(self):
        print("ipv8-lab interactive shell.  Type 'help' for commands.")
        while True:
            try:
                line = input("ipv8> ").strip()
            except (EOFError, KeyboardInterrupt):
                print(); return
            if not line:
                continue
            try:
                toks = shlex.split(line)
            except ValueError as e:
                print(f"parse error: {e}"); continue
            cmd, *args = toks
            if cmd in ("quit", "exit"):
                return
            if cmd == "help":
                print(HELP); continue
            handler = getattr(self, f"cmd_{cmd}", None)
            if handler is None:
                print(f"unknown command: {cmd} (try 'help')"); continue
            try:
                handler(args)
            except Exception as e:
                print(f"error: {e}")


if __name__ == "__main__":
    Shell().run()
