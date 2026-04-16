"""18-link, 10-router composite topology.

Link list (parallel links marked "(redundant)"):

    L01: R1  ── R2        L10: R5  ── R7
    L02: R1  ── R6        L11: R6  ── R7
    L03: R2  ── R3        L12: R7  ── R8
    L04: R2  ── R5        L13: R7  ── R9
    L05: R3  ── R4        L14: R8  ── R9
    L06: R3  ── R5        L15: R8  ── R10
    L07: R4  ── R5        L16: R9  ── R10
    L08: R4  ── R8        L17: R1  ── R2  (redundant of L01)
    L09: R5  ── R6        L18: R4  ── R8  (redundant of L08)

Addressing
----------

Each link Lk has subnet ``10.<k>.0.0/24``; on link k, router Ri gets
``10.<k>.0.<i>``.  So e.g. on L04 (R2–R5), R2=10.4.0.2, R5=10.4.0.5.

Routing
-------

BFS from each router computes the first-hop peer IP for every other
router; a route is then installed for every remote /24 that points at the
first-hop peer closer to that subnet's endpoints.  The primary link is
always picked by BFS because it precedes its redundant counterpart in the
adjacency order.

Tests
-----

* all 90 ordered router pairs reach each other (R1..R10 canonical IP)
* the routing table on a hub-heavy router has the right row count
* bringing down the *primary* R1–R2 link breaks ping until an alternate
  route over the redundant L17 is installed; ditto for the R4–R8 pair
"""

from __future__ import annotations

import unittest
from collections import defaultdict, deque
from typing import Dict, List, Tuple

from ipv8 import IOSCLI, IPv8Address, Network, Router


# --- Topology definition -----------------------------------------------------
LINKS: List[Tuple[str, int, int]] = [
    ("L01", 1, 2),
    ("L02", 1, 6),
    ("L03", 2, 3),
    ("L04", 2, 5),
    ("L05", 3, 4),
    ("L06", 3, 5),
    ("L07", 4, 5),
    ("L08", 4, 8),
    ("L09", 5, 6),
    ("L10", 5, 7),
    ("L11", 6, 7),
    ("L12", 7, 8),
    ("L13", 7, 9),
    ("L14", 8, 9),
    ("L15", 8, 10),
    ("L16", 9, 10),
    ("L17", 1, 2),   # redundant
    ("L18", 4, 8),   # redundant
]

N_ROUTERS = 10


def _ip(link_index: int, router_num: int) -> str:
    return f"10.{link_index}.0.{router_num}"


def _subnet(link_index: int) -> str:
    return f"10.{link_index}.0.0/24"


def _build():
    net = Network()
    routers: Dict[int, Router] = {}
    clis: Dict[str, IOSCLI] = {}

    for i in range(1, N_ROUTERS + 1):
        r = Router(f"R{i}", net.trace)
        net.add_node(r)
        routers[i] = r
        clis[f"R{i}"] = IOSCLI(r)

    # Per-router iface listing
    iface_count: Dict[int, int] = defaultdict(int)
    # router_ifaces[rnum] = [ {name, link_index, neighbor, my_ip, peer_ip} ]
    router_ifaces: Dict[int, List[dict]] = defaultdict(list)

    for idx, (link_name, a, b) in enumerate(LINKS, start=1):
        lnk = net.link(link_name)
        ifa = f"Gig0/{iface_count[a]}"; iface_count[a] += 1
        ifb = f"Gig0/{iface_count[b]}"; iface_count[b] += 1
        routers[a].add_interface(ifa, IPv8Address(0, 0), lnk)
        routers[b].add_interface(ifb, IPv8Address(0, 0), lnk)
        router_ifaces[a].append({
            "name": ifa, "link_index": idx, "neighbor": b,
            "my_ip": _ip(idx, a), "peer_ip": _ip(idx, b),
        })
        router_ifaces[b].append({
            "name": ifb, "link_index": idx, "neighbor": a,
            "my_ip": _ip(idx, b), "peer_ip": _ip(idx, a),
        })

    # --- BFS from every router ------------------------------------------------
    adj: Dict[int, List[dict]] = {
        r: list(router_ifaces[r]) for r in range(1, N_ROUTERS + 1)
    }
    # first_hop[src][dst] = {"iface_name", "peer_ip", "distance"}
    first_hop: Dict[int, Dict[int, dict]] = defaultdict(dict)
    distance: Dict[int, Dict[int, int]] = defaultdict(dict)
    for src in range(1, N_ROUTERS + 1):
        distance[src][src] = 0
        q: deque = deque([src])
        while q:
            node = q.popleft()
            for info in adj[node]:
                nbr = info["neighbor"]
                if nbr in distance[src]:
                    continue
                distance[src][nbr] = distance[src][node] + 1
                if node == src:
                    first_hop[src][nbr] = {
                        "iface_name": info["name"],
                        "peer_ip": info["peer_ip"],
                    }
                else:
                    first_hop[src][nbr] = first_hop[src][node]
                q.append(nbr)

    # --- Configure each router via CLI ----------------------------------------
    for src in range(1, N_ROUTERS + 1):
        cli = clis[f"R{src}"]
        script = ["enable", "configure terminal"]
        # Interface addresses + connected /24 routes
        for info in router_ifaces[src]:
            script += [
                f"interface {info['name']}",
                f"ip address {info['my_ip']}",
                "no shutdown", "exit",
                f"ip route {_subnet(info['link_index'])} interface {info['name']}",
            ]
        # For every non-connected subnet, pick the closer endpoint and install
        # a static route via the first-hop peer that heads toward it.
        my_connected = {info["link_index"] for info in router_ifaces[src]}
        for link_idx, (_, a, b) in enumerate(LINKS, start=1):
            if link_idx in my_connected:
                continue
            da = distance[src].get(a, float("inf"))
            db = distance[src].get(b, float("inf"))
            target = a if da <= db else b
            fh = first_hop[src][target]
            script += [f"ip route {_subnet(link_idx)} {fh['peer_ip']}"]
        script += ["end"]
        cli.run_script(script)

    return net, routers, clis, router_ifaces


def _canonical_ip(rnum: int, router_ifaces) -> str:
    """Pick each router's first-assigned IP as its canonical address."""
    return router_ifaces[rnum][0]["my_ip"]


class TestTopology18Links(unittest.TestCase):

    def test_link_count_is_18(self):
        _, _, _, _ = _build()
        self.assertEqual(len(LINKS), 18)

    def test_interface_counts(self):
        """R5 and R8 are the hubs (5 interfaces each)."""
        _, routers, _, _ = _build()
        self.assertEqual(len(routers[5].interfaces), 5)
        self.assertEqual(len(routers[8].interfaces), 5)
        self.assertEqual(len(routers[2].interfaces), 4)
        self.assertEqual(len(routers[4].interfaces), 4)
        self.assertEqual(len(routers[7].interfaces), 4)
        self.assertEqual(len(routers[1].interfaces), 3)
        self.assertEqual(len(routers[3].interfaces), 3)
        self.assertEqual(len(routers[6].interfaces), 3)
        self.assertEqual(len(routers[9].interfaces), 3)
        self.assertEqual(len(routers[10].interfaces), 2)

    def test_all_pairs_reachable(self):
        net, _, clis, router_ifaces = _build()
        canonical = {i: _canonical_ip(i, router_ifaces) for i in range(1, N_ROUTERS + 1)}
        failures = []
        for src in range(1, N_ROUTERS + 1):
            cli = clis[f"R{src}"]
            cli.mode = "user"
            cli.run_script(["enable"])
            for dst in range(1, N_ROUTERS + 1):
                if src == dst:
                    continue
                cli.run_script([f"ping {canonical[dst]}"])
                if not cli.last_ping_ok:
                    failures.append(f"R{src} -> R{dst} ({canonical[dst]})")
        self.assertEqual([], failures, msg="\n".join(failures))

    def test_r5_is_a_hub_with_13_remote_routes(self):
        """R5 connects to 5 links → 5 connected + 13 remote routes = 18 ASN=0 entries."""
        _, routers, _, _ = _build()
        asn0 = routers[5].rtable.tier1.get(0, [])
        self.assertEqual(
            len(asn0), 18,
            msg=f"R5 has {len(asn0)} ASN=0 routes (expected 5 connected + 13 remote = 18)",
        )

    def test_redundant_r1_r2_link(self):
        """Shut down primary L01; install alternate via L17; ping still works."""
        net, routers, clis, router_ifaces = _build()
        # R1: primary (L01) uses Gig0/0, redundant (L17) uses Gig0/2
        # Shut Gig0/0 on R1 so the connected /24 for 10.1.0.0/24 is unreachable.
        cli1 = clis["R1"]; cli1.mode = "user"
        cli1.run_script([
            "enable", "configure terminal",
            "interface Gig0/0", "shutdown", "end",
        ])
        # Confirm the packet now drops at R1's Gig0/0
        cli1.run_script(["ping 10.1.0.2"])
        self.assertFalse(cli1.last_ping_ok,
                         msg="primary ping should fail with L01 down")
        drops = [e for e in net.trace.events
                 if e.action == "drop" and "admin-down" in e.note and e.node == "R1"]
        self.assertTrue(drops, "expected an egress-admin-down drop at R1")
        # Install /32 redundant route through L17 (more-specific than /24)
        # L17 peer on R2 has IP 10.17.0.2
        cli1.run_script([
            "configure terminal",
            "ip route 10.1.0.2/32 10.17.0.2",
            "end",
        ])
        cli1.run_script(["ping 10.1.0.2"])
        self.assertTrue(cli1.last_ping_ok,
                        msg="redundant-path ping should succeed\n" + cli1.output())

    def test_redundant_r4_r8_link(self):
        """Primary L08 down → alternate L18 used."""
        net, routers, clis, router_ifaces = _build()
        # R4 interfaces in order (as created): L05 (Gig0/0), L07 (Gig0/1), L08 (Gig0/2), L18 (Gig0/3)
        # So L08 is Gig0/2; L18 is Gig0/3.
        cli4 = clis["R4"]; cli4.mode = "user"
        cli4.run_script([
            "enable", "configure terminal",
            "interface Gig0/2", "shutdown", "end",
        ])
        cli4.run_script(["ping 10.8.0.8"])
        self.assertFalse(cli4.last_ping_ok,
                         msg="primary ping should fail with L08 down")
        # Install alternate via L18: R4's Gig0/3 (10.18.0.4) to R8's 10.18.0.8
        cli4.run_script([
            "configure terminal",
            "ip route 10.8.0.8/32 10.18.0.8",
            "end",
        ])
        cli4.run_script(["ping 10.8.0.8"])
        self.assertTrue(cli4.last_ping_ok,
                        msg="redundant-path ping should succeed\n" + cli4.output())

    def test_trace_shows_multihop_path(self):
        """R1 → R10 hits at least 3 intermediate routers (longest expected path)."""
        net, _, clis, router_ifaces = _build()
        cli = clis["R1"]; cli.mode = "user"
        net.trace.events.clear()
        cli.run_script([f"enable", f"ping 10.15.0.10"])  # R10 on L15
        self.assertTrue(cli.last_ping_ok)
        forward_nodes = [e.node for e in net.trace.events if e.action == "forward"]
        # Minimum hops R1 → R10: R1-R2-R5-R7-R8-R10 = 5 hops, or R1-R6-R7-R8-R10 = 4
        # (R1-R6-R7-R8-R10 path: 4 router forwards when counting intermediates
        # that forward — R1 sends, R6/R7/R8 forward, R10 receives.)
        # So expect at least 3 forwarders for the first echo request.
        first_echo_forwarders = forward_nodes[:5]
        self.assertGreaterEqual(
            len(set(first_echo_forwarders)), 3,
            msg=f"first-echo forwarders: {first_echo_forwarders}",
        )


if __name__ == "__main__":
    unittest.main()
