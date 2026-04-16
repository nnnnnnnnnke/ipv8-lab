"""5-router end-to-end test.

Topology (linear chain, one ASN per router):

    hA --[linkA]-- R1 --[link12]-- R2 --[link23]-- R3 --[link34]-- R4 --[link45]-- R5 --[linkB]-- hB

    ASN      : 65001(0.0.253.233)  65002(0.0.253.234)  65003(0.0.253.235)
                                    65004(0.0.253.236)  65005(0.0.253.237)

Every router is configured exclusively through the Cisco-style IOSCLI.
"""

import unittest

from ipv8 import (
    Host,
    IOSCLI,
    IPv8Address,
    Network,
    Router,
)


def addr(asn: int, v4: str) -> IPv8Address:
    return IPv8Address.from_asn_and_ipv4(asn, v4)


# Resolved ASN octet strings for clarity in the CLI scripts.
A = {
    65001: "0.0.253.233",
    65002: "0.0.253.234",
    65003: "0.0.253.235",
    65004: "0.0.253.236",
    65005: "0.0.253.237",
}


class TestFiveRouters(unittest.TestCase):
    def build(self):
        net = Network()
        lA = net.link("linkA")
        l12 = net.link("link12")
        l23 = net.link("link23")
        l34 = net.link("link34")
        l45 = net.link("link45")
        lB = net.link("linkB")

        asns = [65001, 65002, 65003, 65004, 65005]

        a_hA = addr(asns[0], "10.1.1.10")
        hA = Host("hostA", a_hA, net.trace)
        hA.add_interface("eth0", a_hA, lA); hA.gateway_iface = "eth0"
        net.add_node(hA)

        a_hB = addr(asns[4], "10.5.1.20")
        hB = Host("hostB", a_hB, net.trace)
        hB.add_interface("eth0", a_hB, lB); hB.gateway_iface = "eth0"
        net.add_node(hB)

        iface_spec = [
            ("R1", (lA, l12), asns[0]),
            ("R2", (l12, l23), asns[1]),
            ("R3", (l23, l34), asns[2]),
            ("R4", (l34, l45), asns[3]),
            ("R5", (l45, lB), asns[4]),
        ]
        routers = []
        for name, (lhs, rhs), asn in iface_spec:
            r = Router(name, net.trace)
            r.add_interface("Gig0/0", addr(asn, "0.0.0.1"), lhs)
            r.add_interface("Gig0/1", addr(asn, "0.0.0.2"), rhs)
            net.add_node(r)
            routers.append(r)

        # For simplicity we let each router's interfaces stay in its own ASN,
        # and the CLI installs a static route per remote ASN.
        cli_scripts = {
            "R1": [
                "enable", "configure terminal", "hostname R1",
                "interface Gig0/0", f"ipv8 address {A[65001]}.10.1.1.1", "no shutdown", "exit",
                "interface Gig0/1", f"ipv8 address {A[65001]}.10.12.0.1", "no shutdown", "exit",
                f"ipv8 route {A[65001]}.10.1.1.0/24 interface Gig0/0",
                f"ipv8 route {A[65002]}.0.0.0.0/0 {A[65001]}.10.12.0.2",
                f"ipv8 route {A[65003]}.0.0.0.0/0 {A[65001]}.10.12.0.2",
                f"ipv8 route {A[65004]}.0.0.0.0/0 {A[65001]}.10.12.0.2",
                f"ipv8 route {A[65005]}.0.0.0.0/0 {A[65001]}.10.12.0.2",
                "end",
            ],
            "R2": [
                "enable", "configure terminal", "hostname R2",
                "interface Gig0/0", f"ipv8 address {A[65002]}.10.12.0.2", "no shutdown", "exit",
                "interface Gig0/1", f"ipv8 address {A[65002]}.10.23.0.1", "no shutdown", "exit",
                f"ipv8 route {A[65001]}.0.0.0.0/0 {A[65002]}.10.12.0.1",
                f"ipv8 route {A[65003]}.0.0.0.0/0 {A[65002]}.10.23.0.2",
                f"ipv8 route {A[65004]}.0.0.0.0/0 {A[65002]}.10.23.0.2",
                f"ipv8 route {A[65005]}.0.0.0.0/0 {A[65002]}.10.23.0.2",
                "end",
            ],
            "R3": [
                "enable", "configure terminal", "hostname R3",
                "interface Gig0/0", f"ipv8 address {A[65003]}.10.23.0.2", "no shutdown", "exit",
                "interface Gig0/1", f"ipv8 address {A[65003]}.10.34.0.1", "no shutdown", "exit",
                f"ipv8 route {A[65001]}.0.0.0.0/0 {A[65003]}.10.23.0.1",
                f"ipv8 route {A[65002]}.0.0.0.0/0 {A[65003]}.10.23.0.1",
                f"ipv8 route {A[65004]}.0.0.0.0/0 {A[65003]}.10.34.0.2",
                f"ipv8 route {A[65005]}.0.0.0.0/0 {A[65003]}.10.34.0.2",
                "end",
            ],
            "R4": [
                "enable", "configure terminal", "hostname R4",
                "interface Gig0/0", f"ipv8 address {A[65004]}.10.34.0.2", "no shutdown", "exit",
                "interface Gig0/1", f"ipv8 address {A[65004]}.10.45.0.1", "no shutdown", "exit",
                f"ipv8 route {A[65001]}.0.0.0.0/0 {A[65004]}.10.34.0.1",
                f"ipv8 route {A[65002]}.0.0.0.0/0 {A[65004]}.10.34.0.1",
                f"ipv8 route {A[65003]}.0.0.0.0/0 {A[65004]}.10.34.0.1",
                f"ipv8 route {A[65005]}.0.0.0.0/0 {A[65004]}.10.45.0.2",
                "end",
            ],
            "R5": [
                "enable", "configure terminal", "hostname R5",
                "interface Gig0/0", f"ipv8 address {A[65005]}.10.45.0.2", "no shutdown", "exit",
                "interface Gig0/1", f"ipv8 address {A[65005]}.10.5.1.1", "no shutdown", "exit",
                f"ipv8 route {A[65001]}.0.0.0.0/0 {A[65005]}.10.45.0.1",
                f"ipv8 route {A[65002]}.0.0.0.0/0 {A[65005]}.10.45.0.1",
                f"ipv8 route {A[65003]}.0.0.0.0/0 {A[65005]}.10.45.0.1",
                f"ipv8 route {A[65004]}.0.0.0.0/0 {A[65005]}.10.45.0.1",
                f"ipv8 route {A[65005]}.10.5.1.0/24 interface Gig0/1",
                "end",
            ],
        }

        clis = {}
        for r in routers:
            cli = IOSCLI(r)
            cli.run_script(cli_scripts[r.name])
            clis[r.name] = cli
        return net, hA, hB, routers, clis

    def test_host_to_host_ping(self):
        net, hA, hB, routers, clis = self.build()
        hA.ping(hB.address, identifier=0xCAFE, sequence=1)
        net.step()
        self.assertIn(
            (0xCAFE, 1), hA.ping_replies,
            msg="end-to-end 5-router ping failed\n" + net.trace.dump(),
        )

    def test_cli_ping_from_r1_to_r5(self):
        net, hA, hB, routers, clis = self.build()
        r5_addr = routers[4].interfaces["Gig0/1"].address
        cli = clis["R1"]
        cli.run_script([f"ping8 {r5_addr}"])
        self.assertTrue(
            cli.last_ping_ok,
            msg="R1 → R5 ping8 failed\n" + cli.output() + "\n" + net.trace.dump(),
        )

    def test_running_config_round_trip(self):
        net, hA, hB, routers, clis = self.build()
        # Capture running-config text directly (excluding CLI command echoes).
        rc = clis["R3"]._running_config()
        self.assertIn("hostname R3", rc)
        self.assertIn(f"ipv8 address {A[65003]}.10.23.0.2", rc)
        # R3 has 4 static routes (to the other four ASes)
        self.assertEqual(rc.count("\nipv8 route "), 4,
                         msg="unexpected route count:\n" + rc)

    def test_no_route_drops(self):
        net, hA, hB, routers, clis = self.build()
        from ipv8 import build_packet, echo_request
        unknown = addr(65099, "1.1.1.1")
        pkt = build_packet(
            src=hA.address, dst=unknown,
            payload=echo_request(1, 1),
            protocol=58, ttl=64,
        )
        routers[0].forward_once(pkt.to_bytes(), "Gig0/0")
        drops = [e for e in net.trace.events if e.action == "drop"]
        self.assertTrue(any("no-route" in e.note for e in drops))

    def test_ttl_expiry_across_chain(self):
        net, hA, hB, routers, clis = self.build()
        from ipv8 import build_packet, echo_request
        # TTL too small to cross the chain (needs 5 hops at least)
        pkt = build_packet(
            src=hA.address, dst=hB.address,
            payload=echo_request(1, 1),
            protocol=58, ttl=3,
        )
        routers[0].forward_once(pkt.to_bytes(), "Gig0/0")
        net.step()
        drops = [e for e in net.trace.events if e.action == "drop"]
        self.assertTrue(any("ttl-exceeded" in e.note for e in drops))


if __name__ == "__main__":
    unittest.main()
