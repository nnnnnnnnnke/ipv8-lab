"""Ring topology (4 routers).

          R1 -- R2
          |      |
          R4 -- R3

Each router is in its own ASN.  Four hosts hang off four routers.  This
test verifies:
  - Clockwise routing (hA -> hC via R2) works
  - After removing the R1->R2 static route, packets re-home onto the
    counter-clockwise path (R1 -> R4 -> R3) and still reach hC.
"""

from __future__ import annotations

import unittest

from ipv8 import build_packet, echo_request

from tests.helpers import RouterBuilder, addr, asn_str  # noqa: E402


ASNS = {"R1": 65101, "R2": 65102, "R3": 65103, "R4": 65104}


def _build():
    from ipv8 import Network

    net = Network()
    l12 = net.link("l12")
    l23 = net.link("l23")
    l34 = net.link("l34")
    l41 = net.link("l41")
    hA_l = net.link("hA_l")
    hB_l = net.link("hB_l")
    hC_l = net.link("hC_l")
    hD_l = net.link("hD_l")
    b = RouterBuilder(net)

    for name in ("R1", "R2", "R3", "R4"):
        b.router(name)

    # Router inter-links: each side of a link is in that side's own ASN.
    b.attach(b.routers["R1"], "Gi0/0", addr(ASNS["R1"], "10.12.0.1"), l12)
    b.attach(b.routers["R2"], "Gi0/0", addr(ASNS["R2"], "10.12.0.2"), l12)
    b.attach(b.routers["R2"], "Gi0/1", addr(ASNS["R2"], "10.23.0.1"), l23)
    b.attach(b.routers["R3"], "Gi0/0", addr(ASNS["R3"], "10.23.0.2"), l23)
    b.attach(b.routers["R3"], "Gi0/1", addr(ASNS["R3"], "10.34.0.1"), l34)
    b.attach(b.routers["R4"], "Gi0/0", addr(ASNS["R4"], "10.34.0.2"), l34)
    b.attach(b.routers["R4"], "Gi0/1", addr(ASNS["R4"], "10.41.0.1"), l41)
    b.attach(b.routers["R1"], "Gi0/1", addr(ASNS["R1"], "10.41.0.2"), l41)

    # Host links
    b.attach(b.routers["R1"], "Gi1/0", addr(ASNS["R1"], "10.1.0.1"), hA_l)
    b.attach(b.routers["R2"], "Gi1/0", addr(ASNS["R2"], "10.2.0.1"), hB_l)
    b.attach(b.routers["R3"], "Gi1/0", addr(ASNS["R3"], "10.3.0.1"), hC_l)
    b.attach(b.routers["R4"], "Gi1/0", addr(ASNS["R4"], "10.4.0.1"), hD_l)

    hA = b.host("hA", addr(ASNS["R1"], "10.1.0.10"), hA_l)
    hB = b.host("hB", addr(ASNS["R2"], "10.2.0.10"), hB_l)
    hC = b.host("hC", addr(ASNS["R3"], "10.3.0.10"), hC_l)
    hD = b.host("hD", addr(ASNS["R4"], "10.4.0.10"), hD_l)

    # Connected routes
    for rn, hs in [("R1", "10.1.0.0"), ("R2", "10.2.0.0"), ("R3", "10.3.0.0"), ("R4", "10.4.0.0")]:
        b.add_connected(
            b.routers[rn], ASNS[rn],
            int.from_bytes(bytes(int(x) for x in hs.split(".")), "big"),
            24, "Gi1/0",
        )

    # Clockwise preferred path: R1 -> R2 -> R3 -> R4 -> R1
    # Each router points toward its clockwise neighbour as primary for all
    # *other* ASNs, and toward its counter-clockwise neighbour as secondary.
    # We install only the primary now; the secondary is added by the test
    # when the primary is withdrawn.

    # R1
    b.add_static(b.routers["R1"], ASNS["R2"], addr(ASNS["R1"], "10.12.0.2"), "Gi0/0")
    b.add_static(b.routers["R1"], ASNS["R3"], addr(ASNS["R1"], "10.12.0.2"), "Gi0/0")
    b.add_static(b.routers["R1"], ASNS["R4"], addr(ASNS["R1"], "10.12.0.2"), "Gi0/0")

    # R2
    b.add_static(b.routers["R2"], ASNS["R1"], addr(ASNS["R2"], "10.12.0.1"), "Gi0/0")
    b.add_static(b.routers["R2"], ASNS["R3"], addr(ASNS["R2"], "10.23.0.2"), "Gi0/1")
    b.add_static(b.routers["R2"], ASNS["R4"], addr(ASNS["R2"], "10.23.0.2"), "Gi0/1")

    # R3
    b.add_static(b.routers["R3"], ASNS["R1"], addr(ASNS["R3"], "10.23.0.1"), "Gi0/0")
    b.add_static(b.routers["R3"], ASNS["R2"], addr(ASNS["R3"], "10.23.0.1"), "Gi0/0")
    b.add_static(b.routers["R3"], ASNS["R4"], addr(ASNS["R3"], "10.34.0.2"), "Gi0/1")

    # R4
    b.add_static(b.routers["R4"], ASNS["R1"], addr(ASNS["R4"], "10.41.0.2"), "Gi0/1")
    b.add_static(b.routers["R4"], ASNS["R2"], addr(ASNS["R4"], "10.34.0.1"), "Gi0/0")
    b.add_static(b.routers["R4"], ASNS["R3"], addr(ASNS["R4"], "10.34.0.1"), "Gi0/0")

    return net, b, {"hA": hA, "hB": hB, "hC": hC, "hD": hD}


class TestRing(unittest.TestCase):
    def test_clockwise_reachability(self):
        net, b, hosts = _build()
        hA, hC = hosts["hA"], hosts["hC"]
        hA.ping(hC.address, identifier=0x11, sequence=1)
        net.step()
        self.assertIn((0x11, 1), hA.ping_replies,
                      msg="clockwise hA->hC failed\n" + net.trace.dump())
        # Traversed R1 -> R2 -> R3 in the first direction
        forwarders = [e.node for e in net.trace.events if e.action == "forward"][:3]
        self.assertEqual(forwarders, ["R1", "R2", "R3"])

    def test_all_pairs_reachable(self):
        net, b, hosts = _build()
        names = ["hA", "hB", "hC", "hD"]
        fails = []
        for i, sn in enumerate(names):
            for j, dn in enumerate(names):
                if i == j:
                    continue
                src = hosts[sn]
                dst = hosts[dn]
                src.ping_replies.clear()
                src.ping(dst.address, identifier=(i * 10 + j), sequence=1)
                net.step()
                if (i * 10 + j, 1) not in src.ping_replies:
                    fails.append(f"{sn}->{dn}")
        self.assertEqual([], fails, msg="\n".join(fails))

    def test_reconverge_after_route_withdrawal(self):
        net, b, hosts = _build()
        # Withdraw R1's clockwise route to R3
        r1 = b.routers["R1"]
        del r1.rtable.tier1[ASNS["R3"]]
        # Install counter-clockwise alternative
        from ipv8 import Route
        r1.rtable.add(
            Route(
                asn_prefix=ASNS["R3"],
                host_prefix=0, host_prefix_len=0,
                next_hop=addr(ASNS["R1"], "10.41.0.1"),
                interface="Gi0/1",
            )
        )
        # R4 already has a forward for ASNS["R3"] via Gi0/0 (correct)
        hosts["hA"].ping_replies.clear()
        hosts["hA"].ping(hosts["hC"].address, identifier=0xAB, sequence=1)
        net.step()
        # Must take the long way around
        forwarders = [e.node for e in net.trace.events if e.action == "forward"][:3]
        self.assertEqual(
            forwarders, ["R1", "R4", "R3"],
            msg="expected counter-clockwise path\n" + net.trace.dump(),
        )
        self.assertIn((0xAB, 1), hosts["hA"].ping_replies)


if __name__ == "__main__":
    unittest.main()
