"""Cisco-IOS-flavoured CLI for driving an IPv8 Router object.

Supported modes:
    user EXEC       hostname>
    priv EXEC       hostname#          (after 'enable')
    global config   hostname(config)#  (after 'configure terminal')
    iface config    hostname(config-if)#

Supported commands (subset, designed to feel Cisco-like):

    user EXEC:
        enable
        ping8 <a.b.c.d.e.f.g.h>
        show ipv8 interface [brief]
        show ipv8 route
        exit / logout

    priv EXEC:
        disable
        configure terminal
        show running-config
        show ipv8 interface [brief]
        show ipv8 route
        ping8 <addr>
        write memory

    global config:
        hostname <NAME>
        interface <NAME>
        ipv8 route <R.R.R.R.N.N.N.N>/<PREFIX_LEN> <NEXT_HOP>
        ipv8 route <R.R.R.R.N.N.N.N>/<PREFIX_LEN> interface <IFACE>
        no ipv8 route <...>
        end / exit

    interface config:
        ipv8 address <ADDR>
        no shutdown / shutdown
        description <TEXT>
        exit
"""

from __future__ import annotations

import io
import shlex
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .address import IPv8Address
from .routing import Route
from .simulator import Host, Router


MODE_USER = "user"
MODE_PRIV = "priv"
MODE_CONF = "conf"
MODE_CONF_IF = "conf-if"


@dataclass
class _IfaceState:
    """CLI-visible metadata that shadows Interface.admin_down (source of truth)."""

    shutdown: bool = False
    description: str = ""


class IOSCLI:
    """A text-driven CLI bound to a single :class:`Router` (or :class:`Host`).

    The CLI does not create links or interfaces from nothing — interfaces must
    already be attached in the simulator.  Think of this class as ``vtysh``
    for a pre-wired device.
    """

    def __init__(self, device, out: Optional[io.TextIOBase] = None) -> None:
        self.device = device
        self.mode = MODE_USER
        self.current_iface: Optional[str] = None
        self.iface_state: Dict[str, _IfaceState] = {
            name: _IfaceState() for name in device.interfaces
        }
        self.history: List[str] = []
        self._out = out if out is not None else io.StringIO()
        # Captured ping results so programmatic callers can inspect them.
        self.last_ping_ok: Optional[bool] = None

    # --- prompt ---------------------------------------------------------------
    def prompt(self) -> str:
        name = self.device.name
        if self.mode == MODE_USER:
            return f"{name}>"
        if self.mode == MODE_PRIV:
            return f"{name}#"
        if self.mode == MODE_CONF:
            return f"{name}(config)#"
        if self.mode == MODE_CONF_IF:
            return f"{name}(config-if)#"
        raise RuntimeError(f"bad mode {self.mode}")

    # --- I/O helpers ----------------------------------------------------------
    def _write(self, s: str = "") -> None:
        self._out.write(s + "\n")

    def output(self) -> str:
        if isinstance(self._out, io.StringIO):
            return self._out.getvalue()
        return ""

    # --- command entry point --------------------------------------------------
    def run_script(self, lines) -> str:
        """Feed a list of command lines (one string per line). Returns output."""
        if isinstance(lines, str):
            lines = lines.splitlines()
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("!") or line.startswith("#"):
                continue
            self._write(f"{self.prompt()} {line}")
            self.execute(line)
        return self.output()

    def execute(self, line: str) -> None:
        self.history.append(line)
        try:
            toks = shlex.split(line)
        except ValueError as e:
            self._write(f"% parse error: {e}")
            return
        if not toks:
            return
        handler = self._dispatch(self.mode, toks)
        if handler is None:
            self._write(f"% Invalid input detected at '^' marker. ({line!r})")
            return
        try:
            handler(toks)
        except Exception as e:
            self._write(f"% command failed: {e}")

    # --- dispatch table -------------------------------------------------------
    def _dispatch(self, mode: str, toks: List[str]):
        cmd = toks[0]
        if mode == MODE_USER:
            return self._user_cmds().get(cmd)
        if mode == MODE_PRIV:
            return self._priv_cmds().get(cmd)
        if mode == MODE_CONF:
            return self._conf_cmds().get(cmd)
        if mode == MODE_CONF_IF:
            return self._conf_if_cmds().get(cmd)
        return None

    def _user_cmds(self):
        return {
            "enable": self._enable,
            "exit": self._cmd_exit,
            "logout": self._cmd_exit,
            "ping8": self._ping8,
            "ping": self._ping_ipv4,
            "show": self._show,
        }

    def _priv_cmds(self):
        return {
            "disable": self._disable,
            "configure": self._configure,
            "show": self._show,
            "ping8": self._ping8,
            "ping": self._ping_ipv4,
            "write": self._write_mem,
            "exit": self._cmd_exit,
            "end": self._end,
        }

    def _conf_cmds(self):
        return {
            "hostname": self._hostname,
            "interface": self._interface,
            "ipv8": self._conf_ipv8,
            "ip": self._conf_ip,
            "no": self._conf_no,
            "end": self._end,
            "exit": self._exit_conf,
        }

    def _conf_if_cmds(self):
        return {
            "ipv8": self._ifconf_ipv8,
            "ip": self._ifconf_ip,
            "no": self._ifconf_no,
            "shutdown": self._ifconf_shutdown,
            "description": self._ifconf_description,
            "end": self._end,
            "exit": self._exit_if,
        }

    # --- mode transitions -----------------------------------------------------
    def _enable(self, toks):
        self.mode = MODE_PRIV

    def _disable(self, toks):
        self.mode = MODE_USER

    def _configure(self, toks):
        if len(toks) >= 2 and toks[1].startswith("term"):
            self.mode = MODE_CONF
            self._write("Enter configuration commands, one per line.  End with CNTL/Z.")
        else:
            self._write("% usage: configure terminal")

    def _end(self, toks):
        self.mode = MODE_PRIV
        self.current_iface = None

    def _exit_conf(self, toks):
        self.mode = MODE_PRIV

    def _exit_if(self, toks):
        self.mode = MODE_CONF
        self.current_iface = None

    def _cmd_exit(self, toks):
        if self.mode == MODE_USER:
            self.mode = MODE_USER  # no-op at top
        elif self.mode == MODE_PRIV:
            self.mode = MODE_USER

    # --- config: hostname -----------------------------------------------------
    def _hostname(self, toks):
        if len(toks) < 2:
            self._write("% usage: hostname NAME")
            return
        self.device.name = toks[1]

    # --- config: interface ----------------------------------------------------
    def _interface(self, toks):
        if len(toks) < 2:
            self._write("% usage: interface NAME"); return
        name = toks[1]
        if name not in self.device.interfaces:
            self._write(f"% no such interface: {name}")
            return
        self.mode = MODE_CONF_IF
        self.current_iface = name
        self.iface_state.setdefault(name, _IfaceState())

    # --- config: ipv8 route ---------------------------------------------------
    def _conf_ipv8(self, toks):
        if len(toks) >= 2 and toks[1] == "route":
            self._add_route(toks[2:])
        else:
            self._write("% usage: ipv8 route PREFIX/LEN NEXT_HOP | interface IFACE")

    def _conf_no(self, toks):
        if len(toks) >= 3 and toks[1] == "ipv8" and toks[2] == "route":
            self._del_route(toks[3:])
        else:
            self._write(f"% no form not understood: {' '.join(toks)}")

    def _parse_prefix(self, s: str) -> Tuple[int, int, int]:
        """Parse R.R.R.R.N.N.N.N/LEN — returns (asn, host_prefix, host_len).

        The prefix length applies to the host half only; the ASN half is
        matched exactly (Tier-1 lookup is exact-ASN).
        """
        if "/" not in s:
            raise ValueError("prefix must be ADDR/LEN")
        addr_s, len_s = s.rsplit("/", 1)
        plen = int(len_s)
        if not 0 <= plen <= 32:
            raise ValueError("host prefix length must be 0..32")
        a = IPv8Address.from_string(addr_s)
        return a.asn, a.host, plen

    def _add_route(self, args: List[str]):
        if len(args) < 2:
            self._write("% usage: ipv8 route ADDR/LEN NEXT_HOP | interface IFACE")
            return
        try:
            asn, host_pfx, host_len = self._parse_prefix(args[0])
        except ValueError as e:
            self._write(f"% {e}"); return

        if args[1] == "interface":
            if len(args) < 3:
                self._write("% usage: ... interface IFACE"); return
            iface = args[2]
            if iface not in self.device.interfaces:
                self._write(f"% no such interface: {iface}"); return
            next_hop = None
        else:
            try:
                next_hop = IPv8Address.from_string(args[1])
            except ValueError as e:
                self._write(f"% {e}"); return
            iface = self._iface_for_next_hop(next_hop)
            if iface is None:
                self._write(
                    f"% cannot resolve egress interface for next-hop {next_hop} "
                    "(no connected ipv8 address matches)"
                )
                return
        self.device.rtable.add(
            Route(
                asn_prefix=asn,
                host_prefix=host_pfx,
                host_prefix_len=host_len,
                next_hop=next_hop,
                interface=iface,
            )
        )

    def _del_route(self, args: List[str]):
        if not args:
            self._write("% usage: no ipv8 route ADDR/LEN ..."); return
        try:
            asn, host_pfx, host_len = self._parse_prefix(args[0])
        except ValueError as e:
            self._write(f"% {e}"); return
        bucket = self.device.rtable.tier1.get(asn, [])
        bucket[:] = [
            r for r in bucket
            if not (r.host_prefix == host_pfx and r.host_prefix_len == host_len)
        ]
        if not bucket:
            self.device.rtable.tier1.pop(asn, None)

    def _iface_for_next_hop(self, nh: IPv8Address) -> Optional[str]:
        """Pick the interface whose address shares the ASN of the next-hop."""
        # Same-ASN heuristic.  Prefer shared /24 on host half, else any-ASN match.
        best_name, best_score = None, -1
        for name, iface in self.device.interfaces.items():
            if iface.address.asn != nh.asn:
                continue
            score = 0
            if (iface.address.host & 0xFFFFFF00) == (nh.host & 0xFFFFFF00):
                score += 2
            score += 1
            if score > best_score:
                best_name, best_score = name, score
        return best_name

    # --- IPv4-style shortcuts -------------------------------------------------
    # These map 1:1 onto IPv8 ASN=0 operations so the two address spaces are
    # provably identical at the library layer.
    def _conf_ip(self, toks):
        """'ip route 10.0.0.0/24 10.1.1.1' | '... interface Gig0/0'"""
        if len(toks) >= 2 and toks[1] == "route":
            args = toks[2:]
            if len(args) < 2:
                self._write(
                    "% usage: ip route ADDR/LEN NEXT_HOP | interface IFACE"
                )
                return
            pfx_part = args[0]
            if "/" not in pfx_part:
                self._write("% prefix must be ADDR/LEN"); return
            v4_pfx, plen = pfx_part.split("/", 1)
            try:
                IPv8Address.from_string(f"0.0.0.0.{v4_pfx}")
            except ValueError as e:
                self._write(f"% bad prefix: {e}"); return
            full_pfx = f"0.0.0.0.{v4_pfx}/{plen}"
            if args[1] == "interface":
                forwarded = [full_pfx, "interface"] + args[2:]
            else:
                try:
                    IPv8Address.from_string(f"0.0.0.0.{args[1]}")
                except ValueError as e:
                    self._write(f"% bad next-hop: {e}"); return
                forwarded = [full_pfx, f"0.0.0.0.{args[1]}"] + args[2:]
            self._add_route(forwarded)
        else:
            self._write("% usage: ip route PFX/LEN NEXT_HOP | interface IFACE")

    def _ifconf_ip(self, toks):
        """'ip address 10.0.0.1' — equivalent to 'ipv8 address 0.0.0.0.10.0.0.1'."""
        if len(toks) >= 3 and toks[1] == "address":
            v4 = toks[2]
            try:
                addr = IPv8Address.from_string(f"0.0.0.0.{v4}")
            except ValueError as e:
                self._write(f"% {e}"); return
            iface = self.device.interfaces[self.current_iface]
            iface.address = addr
            if isinstance(self.device, Host):
                self.device.address = addr
                self.device.gateway_iface = self.current_iface
        else:
            self._write("% usage: ip address X.X.X.X")

    def _ping_ipv4(self, toks):
        """'ping 10.0.0.1' → internally 'ping8 0.0.0.0.10.0.0.1'."""
        if len(toks) < 2:
            self._write("% usage: ping X.X.X.X"); return
        v4 = toks[1]
        try:
            IPv8Address.from_string(f"0.0.0.0.{v4}")
        except ValueError as e:
            self._write(f"% {e}"); return
        self._ping8(["ping8", f"0.0.0.0.{v4}"])

    # --- interface config -----------------------------------------------------
    def _ifconf_ipv8(self, toks):
        if len(toks) >= 3 and toks[1] == "address":
            try:
                addr = IPv8Address.from_string(toks[2])
            except ValueError as e:
                self._write(f"% {e}"); return
            iface = self.device.interfaces[self.current_iface]
            iface.address = addr
            # Keep the Host.address mirror current if applicable.
            if isinstance(self.device, Host):
                self.device.address = addr
                self.device.gateway_iface = self.current_iface
        else:
            self._write("% usage: ipv8 address ADDR")

    def _ifconf_no(self, toks):
        if len(toks) >= 2 and toks[1] == "shutdown":
            self.iface_state[self.current_iface].shutdown = False
            self.device.interfaces[self.current_iface].admin_down = False
        else:
            self._write(f"% no form not understood: {' '.join(toks)}")

    def _ifconf_shutdown(self, toks):
        self.iface_state[self.current_iface].shutdown = True
        self.device.interfaces[self.current_iface].admin_down = True

    def _ifconf_description(self, toks):
        self.iface_state[self.current_iface].description = " ".join(toks[1:])

    # --- show and ping --------------------------------------------------------
    def _show(self, toks):
        if len(toks) >= 2 and toks[1] == "ipv8":
            if len(toks) >= 3 and toks[2] == "interface":
                self._show_iface(brief=(len(toks) >= 4 and toks[3].startswith("br")))
                return
            if len(toks) >= 3 and toks[2] == "route":
                self._show_route(); return
        if len(toks) >= 2 and toks[1] == "ip":
            if len(toks) >= 3 and toks[2] == "route":
                self._show_ip_route(); return
            if len(toks) >= 3 and toks[2] == "interface":
                self._show_ip_interface(brief=(len(toks) >= 4 and toks[3].startswith("br")))
                return
        if len(toks) >= 2 and toks[1].startswith("running"):
            self._write(self._running_config()); return
        self._write(f"% usage: show ipv8 interface|route  |  show ip route|interface")

    def _show_iface(self, brief: bool) -> None:
        if brief:
            self._write("Interface            IPv8 Address                          Status")
            for name, iface in self.device.interfaces.items():
                st = self.iface_state.get(name, _IfaceState())
                status = "down" if st.shutdown else "up"
                self._write(f"{name:<20s} {str(iface.address):<38s} {status}")
            return
        for name, iface in self.device.interfaces.items():
            st = self.iface_state.get(name, _IfaceState())
            admin = "administratively down" if st.shutdown else "up"
            self._write(f"{name} is {admin}, line protocol is {admin}")
            self._write(f"  Description: {st.description or '(none)'}")
            self._write(f"  Internet8 address is {iface.address}")
            self._write(f"  ASN {iface.address.asn} (r.r.r.r = "
                        f"{'.'.join(str(o) for o in iface.address.asn_octets)})")

    def _show_route(self) -> None:
        self._write("Codes: C - connected, S - static")
        self._write("Two-tier IPv8 routing table (draft-thain-ipv8-00)")
        if not self.device.rtable.tier1 and not self.device.rtable.default:
            self._write("  (no routes)")
            return
        # Connected routes (synthesised from interface config)
        for name, iface in self.device.interfaces.items():
            self._write(
                f"  C  ASN {iface.address.asn} "
                f"{iface.address.ipv4_string}/32 direct  dev {name}"
            )
        # Static routes
        for asn, routes in sorted(self.device.rtable.tier1.items()):
            for r in routes:
                nh = str(r.next_hop) if r.next_hop else "connected"
                host_ip = ".".join(
                    str((r.host_prefix >> (24 - 8 * i)) & 0xFF) for i in range(4)
                )
                self._write(
                    f"  S  ASN {asn} {host_ip}/{r.host_prefix_len} "
                    f"via {nh} dev {r.interface}"
                )
        if self.device.rtable.default:
            r = self.device.rtable.default
            nh = str(r.next_hop) if r.next_hop else "connected"
            self._write(f"  S* default via {nh} dev {r.interface}")

    # --- show ip (IPv4 narrowed view) -----------------------------------------
    def _show_ip_route(self) -> None:
        """List only the ASN=0 (IPv4-compat) portion of the routing table."""
        self._write("Codes: C - connected, S - static")
        ipv4_ifaces = [
            (name, iface) for name, iface in self.device.interfaces.items()
            if iface.address.asn == 0 and iface.address.host != 0
        ]
        if not ipv4_ifaces and not self.device.rtable.tier1.get(0):
            self._write("  (no IPv4 routes)")
            return
        for name, iface in ipv4_ifaces:
            self._write(
                f"  C  {iface.address.ipv4_string}/32 is directly connected, {name}"
            )
        for r in self.device.rtable.tier1.get(0, []):
            host_ip = ".".join(
                str((r.host_prefix >> (24 - 8 * i)) & 0xFF) for i in range(4)
            )
            if r.next_hop:
                self._write(
                    f"  S  {host_ip}/{r.host_prefix_len} [1/0] "
                    f"via {r.next_hop.ipv4_string}, {r.interface}"
                )
            else:
                self._write(
                    f"  S  {host_ip}/{r.host_prefix_len} is directly connected, {r.interface}"
                )

    def _show_ip_interface(self, brief: bool) -> None:
        if brief:
            self._write(f"{'Interface':<22s} {'IP-Address':<15s} Status")
            for name, iface in self.device.interfaces.items():
                if iface.address.asn != 0:
                    continue
                status = "administratively down" if iface.admin_down else "up"
                ip = iface.address.ipv4_string
                self._write(f"{name:<22s} {ip:<15s} {status}")
            return
        for name, iface in self.device.interfaces.items():
            if iface.address.asn != 0:
                continue
            admin = "administratively down" if iface.admin_down else "up"
            self._write(f"{name} is {admin}, line protocol is {admin}")
            self._write(f"  Internet address is {iface.address.ipv4_string}/32")
            self._write("  IPv4-compat (IPv8 ASN=0 backward compatibility mode)")

    def _running_config(self) -> str:
        lines = [f"hostname {self.device.name}", "!"]
        for name, iface in self.device.interfaces.items():
            st = self.iface_state.get(name, _IfaceState())
            lines.append(f"interface {name}")
            if st.description:
                lines.append(f" description {st.description}")
            lines.append(f" ipv8 address {iface.address}")
            lines.append(" shutdown" if st.shutdown else " no shutdown")
            lines.append("!")
        for asn, routes in sorted(self.device.rtable.tier1.items()):
            for r in routes:
                host_ip = ".".join(
                    str((r.host_prefix >> (24 - 8 * i)) & 0xFF) for i in range(4)
                )
                addr = f"{'.'.join(str(o) for o in _asn_octets(asn))}.{host_ip}"
                if r.next_hop:
                    lines.append(
                        f"ipv8 route {addr}/{r.host_prefix_len} {r.next_hop}"
                    )
                else:
                    lines.append(
                        f"ipv8 route {addr}/{r.host_prefix_len} interface {r.interface}"
                    )
        lines.append("end")
        return "\n".join(lines)

    def _ping8(self, toks):
        if len(toks) < 2:
            self._write("% usage: ping8 ADDR"); return
        try:
            target = IPv8Address.from_string(toks[1])
        except ValueError as e:
            self._write(f"% {e}"); return
        net = getattr(self.device, "_net", None)
        if net is None:
            self._write("% device is not attached to a running Network")
            return
        # Pick source + egress interface:  follow the routing table so a
        # router picks the interface that actually reaches the destination,
        # not just its first port.
        if isinstance(self.device, Host):
            src = self.device.address
            iface = self.device.gateway_iface or next(iter(self.device.interfaces))
        else:
            route = self.device.rtable.lookup(target)
            if route is not None:
                iface = route.interface
                src = self.device.interfaces[iface].address
            else:
                iface_name, iface_obj = next(iter(self.device.interfaces.items()))
                src = iface_obj.address
                iface = iface_name
        self._write(
            f"Type escape sequence to abort.\n"
            f"Sending 5, 0-byte IPv8 Echos to {target}, timeout is 2 seconds:"
        )
        success = 0
        from .icmp import echo_request
        from .packet import build_packet
        from .constants import PROTO_ICMPV8
        for seq in range(1, 6):
            # Reset reply tracking
            if hasattr(self.device, "ping_replies"):
                self.device.ping_replies = []
            pkt = build_packet(
                src=src, dst=target,
                payload=echo_request(0xBEEF, seq),
                protocol=PROTO_ICMPV8, ttl=64,
            )
            self.device.trace.log(self.device.name, "send", pkt, note=f"ping8 seq={seq}")
            self.device._send_on(iface, pkt)
            net.step()
            got = hasattr(self.device, "ping_replies") and (0xBEEF, seq) in self.device.ping_replies
            success += int(got)
        dots = "".join("!" if success > i else "." for i in range(5))
        self._write(dots)
        rate = success * 100 // 5
        self._write(
            f"Success rate is {rate} percent ({success}/5)"
        )
        self.last_ping_ok = success > 0

    def _write_mem(self, toks):
        self._write("Building configuration...\n[OK]")


def _asn_octets(asn: int) -> Tuple[int, int, int, int]:
    return (
        (asn >> 24) & 0xFF,
        (asn >> 16) & 0xFF,
        (asn >> 8) & 0xFF,
        asn & 0xFF,
    )
