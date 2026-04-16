#!/usr/bin/env python3
"""Interactive Cisco-style IOS shell over the 5-router demo topology.

Usage:
    python3 ios_shell.py            # attach to R1 by default
    python3 ios_shell.py R3         # attach to R3 on start

Special commands (available in every mode):
    attach <R1..R5>    switch to another router's console
    hosts              list hosts + addresses
    routers            list routers + interfaces
    show trace         dump the tcpdump-style packet trace
    ping from <H> to <ADDR> [<id> [<seq>]]   ping from a host instead of a router
    clear trace        reset the trace log
    quit / exit        leave the shell
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.test_five_routers import TestFiveRouters


BANNER = r"""
 ___ ______     _____  _      ____
|_ _|  _ \ \   / ( _ )| |    / ___|
 | || |_) \ \ / // _ \| |   | |
 | ||  __/ \ V /| (_) | |___| |___
|___|_|     \_/  \___/|_____|\____| interactive IOS shell

                      (ipv8-lab / draft-thain-ipv8-00)

5-router linear topology already built:
    hostA -- R1 == R2 == R3 == R4 == R5 -- hostB
       AS 65001   65002   65003   65004   65005

Tips
  attach R2              switch console to router R2
  enable                 user EXEC → priv EXEC
  configure terminal     priv EXEC → config
  show ipv8 route        print this router's routing table
  ping8 <ADDR>           ICMPv8 echo from this router
  ping from hostA to 0.0.253.237.10.5.1.20
  show trace             dump tcpdump-style packet history
  quit                   leave
"""


def main() -> int:
    t = TestFiveRouters()
    net, hA, hB, routers, clis = t.build()
    hosts = {h.name: h for h in (hA, hB)}

    start = sys.argv[1] if len(sys.argv) > 1 else "R1"
    if start not in clis:
        print(f"no such router: {start}")
        return 2
    current = start

    print(BANNER)
    while True:
        cli = clis[current]
        try:
            raw = input(cli.prompt() + " ")
        except (EOFError, KeyboardInterrupt):
            print(); return 0
        line = raw.strip()
        if not line:
            continue

        # Meta commands (not forwarded to IOSCLI)
        if line in ("quit", ":q"):
            return 0
        if line.startswith("attach"):
            toks = line.split()
            if len(toks) == 2 and toks[1] in clis:
                current = toks[1]
                print(f"(now on {current}; type 'enable' to go priv)")
            else:
                print(f"usage: attach {{{'|'.join(clis)}}}")
            continue
        if line == "routers":
            for name, r in clis.items():
                ifs = ", ".join(
                    f"{i}={iface.address}" for i, iface in r.device.interfaces.items()
                )
                print(f"  {name:<4s} {ifs}")
            continue
        if line == "hosts":
            for name, h in hosts.items():
                print(f"  {name:<7s} addr={h.address}")
            continue
        if line == "show trace":
            dump = net.trace.dump()
            print(dump if dump else "(empty)")
            continue
        if line == "clear trace":
            net.trace.events.clear()
            print("trace cleared.")
            continue
        if line.startswith("ping from "):
            try:
                # "ping from <H> to <ADDR> [<id> [<seq>]]"
                parts = line.split()
                assert parts[0] == "ping" and parts[1] == "from"
                hname = parts[2]
                assert parts[3] == "to"
                target_s = parts[4]
                ident = int(parts[5]) if len(parts) > 5 else 0xBEEF
                seq = int(parts[6]) if len(parts) > 6 else 1
            except Exception:
                print("usage: ping from <hostA|hostB> to <ADDR> [<id> [<seq>]]")
                continue
            from ipv8 import IPv8Address
            if hname not in hosts:
                print(f"no such host: {hname}")
                continue
            try:
                target = IPv8Address.from_string(target_s)
            except ValueError as e:
                print(f"bad address: {e}")
                continue
            h = hosts[hname]
            h.ping_replies.clear()
            h.ping(target, identifier=ident, sequence=seq)
            net.step()
            ok = (ident, seq) in h.ping_replies
            print(f"{hname} -> {target}: {'reply received' if ok else 'NO REPLY'}")
            continue

        # Delegate everything else to the IOS CLI and print the new output
        before = len(cli._out.getvalue())
        cli.execute(line)
        new_out = cli._out.getvalue()[before:]
        if new_out:
            sys.stdout.write(new_out)


if __name__ == "__main__":
    sys.exit(main())
