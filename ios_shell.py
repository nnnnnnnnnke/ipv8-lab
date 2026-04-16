#!/usr/bin/env python3
"""Interactive Cisco-IOS-flavoured shell — build your own router-only topology.

Usage:
    python3 ios_shell.py

Meta commands (only valid in this shell, not real IOS):
    router add <NAME>                          create a router + auto-attach
    router remove <NAME>                       delete a router and detach its links
    link add <LINK> <Ra>:<Ifa> <Rb>:<Ifb>      create a link and two interfaces
    link remove <LINK>                         tear down a link (+ detach interfaces)
    attach <NAME>                              switch console to another router
    routers                                    list routers + their interfaces
    links                                      list links + their endpoints
    show trace                                 dump the simulator's tcpdump log
    clear trace                                reset the trace
    quit / :q                                  leave the shell

All other commands are forwarded to Cisco-style IOS.
Typical flow:

    router add R1
    router add R2
    link add L12 R1:Gig0/0 R2:Gig0/0
    attach R1
    enable
    configure terminal
    interface Gig0/0
     ipv8 address 0.0.253.233.10.0.0.1
     no shutdown
     exit
    ipv8 route 0.0.253.234.0.0.0.0/0 0.0.253.233.10.0.0.2
    end
    attach R2
    enable
    configure terminal
    interface Gig0/0
     ipv8 address 0.0.253.234.10.0.0.2
     no shutdown
     exit
    ipv8 route 0.0.253.233.0.0.0.0/0 0.0.253.234.10.0.0.1
    end
    ping8 0.0.253.233.10.0.0.1
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipv8 import IOSCLI, IPv8Address, Network, Router


BANNER = r"""
 ___ ______     _____  _      ____
|_ _|  _ \ \   / ( _ )| |    / ___|
 | || |_) \ \ / // _ \| |   | |
 | ||  __/ \ V /| (_) | |___| |___
|___|_|     \_/  \___/|_____|\____| interactive IOS shell

Router-only sandbox.  Start building a topology with:
    router add R1
    router add R2
    link add L12 R1:Gig0/0 R2:Gig0/0
    attach R1
Type 'quit' to leave.  Full meta reference:  'help-meta'
"""


PLACEHOLDER_ADDR = IPv8Address(0, 0)  # 0.0.0.0.0.0.0.0 — "unassigned"


HELP_META = """\
Meta commands:
  router add <NAME>                          create router (auto-attach)
  router remove <NAME>                       delete router
  link add <LINK> <Ra>:<Ifa> <Rb>:<Ifb>      create link + interfaces
  link remove <LINK>                         tear down link
  attach <NAME>                              switch console
  routers                                    list routers + interfaces
  links                                      list links + endpoints
  show trace                                 dump simulator event log
  clear trace                                reset trace
  help-meta                                  show this help
  quit / :q                                  leave
IOS commands (user/priv/config/config-if):
  enable / disable / configure terminal / end / exit
  hostname <NAME>
  interface <IFACE>
    ipv8 address <ADDR>
    no shutdown / shutdown
    description <TEXT>
    exit
  ipv8 route <PFX>/<LEN> <NEXT_HOP>
  ipv8 route <PFX>/<LEN> interface <IFACE>
  no ipv8 route <PFX>/<LEN>
  show ipv8 interface [brief]
  show ipv8 route
  show running-config
  ping8 <ADDR>"""


class Shell:
    def __init__(self) -> None:
        self.net = Network()
        self.clis: dict[str, IOSCLI] = {}
        self.current: str | None = None

    # --- prompt / I/O helpers ------------------------------------------------
    def prompt(self) -> str:
        if self.current is None:
            return "ipv8lab> "
        return self.clis[self.current].prompt() + " "

    # --- main loop -----------------------------------------------------------
    def run(self) -> int:
        print(BANNER)
        while True:
            try:
                raw = input(self.prompt())
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            line = raw.strip()
            if not line:
                continue
            if self._meta(line):
                continue
            if self.current is None:
                print("% no router attached.  Try 'router add R1' first.")
                continue
            cli = self.clis[self.current]
            before = len(cli._out.getvalue())
            cli.execute(line)
            new_out = cli._out.getvalue()[before:]
            if new_out:
                sys.stdout.write(new_out)

    # --- meta dispatch -------------------------------------------------------
    def _meta(self, line: str) -> bool:
        toks = line.split()
        cmd = toks[0]

        if cmd in ("quit", ":q"):
            sys.exit(0)
        if cmd in ("help-meta", "?"):
            print(HELP_META)
            return True
        if cmd == "attach":
            return self._attach(toks[1:])
        if cmd == "routers":
            self._list_routers()
            return True
        if cmd == "links":
            self._list_links()
            return True
        if cmd == "router":
            self._cmd_router(toks[1:])
            return True
        if cmd == "link":
            self._cmd_link(toks[1:])
            return True
        if line == "show trace":
            dump = self.net.trace.dump()
            print(dump if dump else "(empty)")
            return True
        if line == "clear trace":
            self.net.trace.events.clear()
            print("trace cleared.")
            return True
        return False

    # --- router commands -----------------------------------------------------
    def _cmd_router(self, args: list[str]) -> None:
        if not args:
            print("usage: router add <NAME>   |   router remove <NAME>")
            return
        if args[0] == "add":
            if len(args) != 2:
                print("usage: router add <NAME>"); return
            name = args[1]
            if name in self.clis:
                print(f"router {name} already exists"); return
            r = Router(name, self.net.trace)
            self.net.add_node(r)
            self.clis[name] = IOSCLI(r)
            self.current = name
            print(f"(created router {name} — now attached; type 'enable' to go priv)")
            return
        if args[0] == "remove":
            if len(args) != 2:
                print("usage: router remove <NAME>"); return
            name = args[1]
            if name not in self.clis:
                print(f"no such router: {name}"); return
            r = self.clis[name].device
            # detach from every link
            for iface_name, iface in list(r.interfaces.items()):
                if iface.link is not None:
                    key = f"{name}/{iface_name}"
                    iface.link.endpoints.pop(key, None)
                    iface.link.queues.pop(key, None)
            self.net.nodes.pop(name, None)
            self.clis.pop(name, None)
            if self.current == name:
                self.current = next(iter(self.clis), None)
            print(f"removed router {name}")
            return
        print("usage: router add <NAME>   |   router remove <NAME>")

    # --- link commands -------------------------------------------------------
    def _cmd_link(self, args: list[str]) -> None:
        if not args:
            print("usage: link add <LINK> <Ra>:<Ifa> <Rb>:<Ifb>   |   link remove <LINK>")
            return
        if args[0] == "add":
            if len(args) != 4:
                print("usage: link add <LINK> <Ra>:<Ifa> <Rb>:<Ifb>"); return
            link_name = args[1]
            try:
                ra, ifa = args[2].split(":", 1)
                rb, ifb = args[3].split(":", 1)
            except ValueError:
                print("endpoint syntax: <Router>:<Iface>  (e.g. R1:Gig0/0)"); return
            for rname in (ra, rb):
                if rname not in self.clis:
                    print(f"unknown router: {rname}"); return
            if link_name in self.net.links:
                print(f"link {link_name} already exists"); return
            if ifa in self.clis[ra].device.interfaces:
                print(f"{ra} already has interface {ifa}"); return
            if ifb in self.clis[rb].device.interfaces:
                print(f"{rb} already has interface {ifb}"); return
            link = self.net.link(link_name)
            self.clis[ra].device.add_interface(ifa, PLACEHOLDER_ADDR, link)
            self.clis[rb].device.add_interface(ifb, PLACEHOLDER_ADDR, link)
            print(
                f"link {link_name}: {ra}:{ifa} ⇄ {rb}:{ifb}  "
                f"(addresses unset — configure with 'interface {ifa}' then 'ipv8 address ...')"
            )
            return
        if args[0] == "remove":
            if len(args) != 2:
                print("usage: link remove <LINK>"); return
            link_name = args[1]
            if link_name not in self.net.links:
                print(f"no such link: {link_name}"); return
            link = self.net.links[link_name]
            for key in list(link.endpoints.keys()):
                router_name, iface_name = key.split("/", 1)
                if router_name in self.clis:
                    self.clis[router_name].device.interfaces.pop(iface_name, None)
            self.net.links.pop(link_name)
            print(f"removed link {link_name}")
            return
        print("usage: link add <LINK> <Ra>:<Ifa> <Rb>:<Ifb>   |   link remove <LINK>")

    # --- listing helpers -----------------------------------------------------
    def _attach(self, args: list[str]) -> bool:
        if len(args) != 1:
            print("usage: attach <ROUTER>")
            return True
        name = args[0]
        if name not in self.clis:
            print(f"no such router: {name}")
            return True
        self.current = name
        # Treat 'attach' as a fresh console session: reset to user EXEC so
        # the familiar enable/configure flow works every time.
        self.clis[name].mode = "user"
        self.clis[name].current_iface = None
        print(f"(now on {name}; type 'enable' to go priv)")
        return True

    def _list_routers(self) -> None:
        if not self.clis:
            print("(no routers yet — 'router add <NAME>' to create one)")
            return
        for name, cli in self.clis.items():
            r = cli.device
            if not r.interfaces:
                print(f"  {name:<10s} (no interfaces)")
                continue
            for iface_name, iface in r.interfaces.items():
                status = "admin-down" if iface.admin_down else "up"
                print(f"  {name:<10s} {iface_name:<12s} {iface.address!s:<38s} [{status}]")

    def _list_links(self) -> None:
        if not self.net.links:
            print("(no links yet — 'link add <LINK> <Ra>:<Ifa> <Rb>:<Ifb>')")
            return
        for link_name, link in self.net.links.items():
            eps = " ⇄ ".join(link.endpoints.keys()) or "(unattached)"
            print(f"  {link_name:<10s} {eps}")


if __name__ == "__main__":
    sys.exit(Shell().run())
