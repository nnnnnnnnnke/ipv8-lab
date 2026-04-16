import unittest

from ipv8 import (
    Host,
    IPv8Address,
    Network,
    PROTO_ICMPV8,
    Route,
    Router,
)


def _build_two_as_topology():
    """
      hostA (AS 64496, 192.168.1.10)
        \\
         linkA -- R1 (AS 64496 border) -- linkCore -- R2 (AS 64497 border) -- linkB
                                                                              /
                                                                   hostB (AS 64497, 10.0.0.5)
    """
    net = Network()
    linkA = net.link("linkA")
    linkCore = net.link("linkCore")
    linkB = net.link("linkB")

    addr_A = IPv8Address.from_asn_and_ipv4(64496, "192.168.1.10")
    addr_B = IPv8Address.from_asn_and_ipv4(64497, "10.0.0.5")
    addr_R1_a = IPv8Address.from_asn_and_ipv4(64496, "192.168.1.1")
    addr_R1_core = IPv8Address.from_asn_and_ipv4(64496, "222.0.0.1")
    addr_R2_core = IPv8Address.from_asn_and_ipv4(64497, "222.0.0.2")
    addr_R2_b = IPv8Address.from_asn_and_ipv4(64497, "10.0.0.1")

    hA = Host("hostA", addr_A, net.trace)
    hA.add_interface("eth0", addr_A, linkA)
    hA.gateway_iface = "eth0"

    hB = Host("hostB", addr_B, net.trace)
    hB.add_interface("eth0", addr_B, linkB)
    hB.gateway_iface = "eth0"

    R1 = Router("R1", net.trace)
    R1.add_interface("ethA", addr_R1_a, linkA)
    R1.add_interface("ethCore", addr_R1_core, linkCore)

    R2 = Router("R2", net.trace)
    R2.add_interface("ethCore", addr_R2_core, linkCore)
    R2.add_interface("ethB", addr_R2_b, linkB)

    # Routing — R1
    R1.rtable.add(
        Route(
            asn_prefix=64496,
            host_prefix=0xC0A80100, host_prefix_len=24,
            next_hop=None, interface="ethA",
        )
    )
    R1.rtable.add(
        Route(
            asn_prefix=64497,
            host_prefix=0, host_prefix_len=0,
            next_hop=addr_R2_core, interface="ethCore",
        )
    )
    # Routing — R2
    R2.rtable.add(
        Route(
            asn_prefix=64497,
            host_prefix=0x0A000000, host_prefix_len=8,
            next_hop=None, interface="ethB",
        )
    )
    R2.rtable.add(
        Route(
            asn_prefix=64496,
            host_prefix=0, host_prefix_len=0,
            next_hop=addr_R1_core, interface="ethCore",
        )
    )
    for n in (hA, hB, R1, R2):
        net.add_node(n)
    return net, hA, hB, R1, R2


class TestSimulator(unittest.TestCase):
    def test_cross_as_ping(self):
        net, hA, hB, R1, R2 = _build_two_as_topology()
        hA.ping(hB.address, identifier=7, sequence=1)
        net.step()
        self.assertIn((7, 1), hA.ping_replies)
        # Trace should contain forward events from both routers
        kinds = [(e.node, e.action) for e in net.trace.events]
        self.assertIn(("R1", "forward"), kinds)
        self.assertIn(("R2", "forward"), kinds)
        self.assertIn(("hostB", "recv"), kinds)
        self.assertIn(("hostA", "recv"), kinds)

    def test_ttl_exceeded(self):
        net, hA, hB, R1, R2 = _build_two_as_topology()
        # Craft a packet with TTL=1 and send it directly to R1
        from ipv8 import build_packet, echo_request
        pkt = build_packet(
            src=hA.address, dst=hB.address,
            payload=echo_request(1, 1),
            protocol=PROTO_ICMPV8, ttl=1,
        )
        # R1 receives; since TTL<=1 at the check, it drops
        R1.forward_once(pkt.to_bytes(), "ethA")
        drops = [e for e in net.trace.events if e.action == "drop"]
        self.assertTrue(any("ttl-exceeded" in e.note for e in drops))

    def test_no_route(self):
        net, hA, hB, R1, R2 = _build_two_as_topology()
        # Send from hostA to a totally unknown ASN
        from ipv8 import build_packet
        unknown = IPv8Address.from_asn_and_ipv4(65000, "1.1.1.1")
        pkt = build_packet(src=hA.address, dst=unknown, payload=b"", protocol=17)
        R1.forward_once(pkt.to_bytes(), "ethA")
        drops = [e for e in net.trace.events if e.action == "drop"]
        self.assertTrue(any("no-route" in e.note for e in drops))


if __name__ == "__main__":
    unittest.main()
