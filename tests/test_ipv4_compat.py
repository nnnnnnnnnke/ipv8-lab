"""Backward-compatibility: IPv4 address == IPv8 with ASN=0.

These tests verify on multiple levels that
  ``ip address 10.0.0.1``
is exactly equivalent to
  ``ipv8 address 0.0.0.0.10.0.0.1``
and that traffic between such addresses routes correctly.
"""

import unittest

from ipv8 import IOSCLI, IPv8Address, Network, Route, Router


class TestAddressLevelCompat(unittest.TestCase):
    """IPv8Address ASN=0 form equals the IPv4-compat constructor."""

    def test_ipv4_compat_equals_ipv8_asn0(self):
        for v4 in ["10.0.0.1", "192.168.1.254", "8.8.8.8", "0.0.0.0", "255.255.255.255"]:
            a = IPv8Address.ipv4_compat(v4)
            b = IPv8Address.from_string(f"0.0.0.0.{v4}")
            self.assertEqual(a, b, f"mismatch for {v4}")
            self.assertEqual(a.to_bytes(), b.to_bytes())
            self.assertEqual(a.ipv4_string, v4)

    def test_ipv4_compat_classification(self):
        a = IPv8Address.from_string("0.0.0.0.192.168.1.1")
        self.assertTrue(a.is_ipv4_compat())
        self.assertEqual(a.classify(), "ipv4-compat")
        self.assertEqual(a.asn, 0)
        self.assertEqual(a.ipv4_string, "192.168.1.1")

    def test_first_byte_on_wire_matches_asn0(self):
        """The on-wire bytes of ipv4_compat() must start with four zero bytes."""
        a = IPv8Address.ipv4_compat("10.1.2.3")
        raw = a.to_bytes()
        self.assertEqual(raw[:4], b"\x00\x00\x00\x00")
        self.assertEqual(raw[4:], b"\x0a\x01\x02\x03")


class TestCLICompat(unittest.TestCase):
    """Confirm the IOS CLI accepts either form and produces identical state."""

    def _single_router(self) -> tuple[Router, IOSCLI]:
        net = Network()
        link = net.link("L")
        r = Router("R", net.trace)
        r.add_interface("Gig0/0", IPv8Address(0, 0), link)
        net.add_node(r)
        return r, IOSCLI(r)

    def test_ip_address_matches_ipv8_form(self):
        r1, cli1 = self._single_router()
        r2, cli2 = self._single_router()
        # Form A: IPv4-style
        cli1.run_script([
            "enable", "configure terminal",
            "interface Gig0/0",
            "ip address 192.168.7.1",
            "no shutdown", "end",
        ])
        # Form B: IPv8 native ASN=0
        cli2.run_script([
            "enable", "configure terminal",
            "interface Gig0/0",
            "ipv8 address 0.0.0.0.192.168.7.1",
            "no shutdown", "end",
        ])
        self.assertEqual(
            r1.interfaces["Gig0/0"].address,
            r2.interfaces["Gig0/0"].address,
            "ip and ipv8 forms produced different addresses",
        )
        self.assertEqual(
            r1.interfaces["Gig0/0"].address.to_bytes(),
            r2.interfaces["Gig0/0"].address.to_bytes(),
        )

    def test_ip_route_matches_ipv8_form(self):
        r1, cli1 = self._single_router()
        r2, cli2 = self._single_router()
        cli1.run_script([
            "enable", "configure terminal",
            "interface Gig0/0",
            "ip address 10.0.0.1", "no shutdown", "exit",
            "ip route 10.1.0.0/16 10.0.0.2",
            "end",
        ])
        cli2.run_script([
            "enable", "configure terminal",
            "interface Gig0/0",
            "ipv8 address 0.0.0.0.10.0.0.1", "no shutdown", "exit",
            "ipv8 route 0.0.0.0.10.1.0.0/16 0.0.0.0.10.0.0.2",
            "end",
        ])
        self.assertEqual(
            list(r1.rtable.tier1.keys()),
            list(r2.rtable.tier1.keys()),
        )
        r1_routes = [
            (r.host_prefix, r.host_prefix_len, r.next_hop)
            for r in r1.rtable.tier1.get(0, [])
        ]
        r2_routes = [
            (r.host_prefix, r.host_prefix_len, r.next_hop)
            for r in r2.rtable.tier1.get(0, [])
        ]
        self.assertEqual(r1_routes, r2_routes)

    def test_show_ip_route_vs_show_ipv8_route(self):
        r, cli = self._single_router()
        cli.run_script([
            "enable", "configure terminal",
            "interface Gig0/0",
            "ip address 10.0.0.1", "no shutdown", "exit",
            "ip route 10.99.0.0/16 10.0.0.2",
            "end",
            "show ip route",
            "show ipv8 route",
        ])
        out = cli.output()
        self.assertIn("10.99.0.0/16", out)
        self.assertIn("10.0.0.2", out)
        # Native IPv8 view must contain the same route expressed under ASN 0
        self.assertIn("ASN 0", out)


class TestPingCompat(unittest.TestCase):
    """Two routers talking purely in IPv4 form — routing must work."""

    def test_two_router_ping_via_ip_commands(self):
        net = Network()
        link = net.link("L12")
        r1 = Router("R1", net.trace); net.add_node(r1)
        r2 = Router("R2", net.trace); net.add_node(r2)
        r1.add_interface("Gig0/0", IPv8Address(0, 0), link)
        r2.add_interface("Gig0/0", IPv8Address(0, 0), link)
        cli1 = IOSCLI(r1); cli2 = IOSCLI(r2)
        for cli, ip in [(cli1, "10.0.0.1"), (cli2, "10.0.0.2")]:
            cli.run_script([
                "enable", "configure terminal",
                "interface Gig0/0",
                f"ip address {ip}", "no shutdown", "exit",
                "ip route 10.0.0.0/24 interface Gig0/0",
                "end",
            ])
        cli1.run_script(["ping 10.0.0.2"])
        self.assertTrue(cli1.last_ping_ok,
                        msg="R1 could not ping R2 via IPv4-compat\n" + cli1.output())

    def test_ipv8_and_ip_interoperate(self):
        """R1 uses 'ip address', R2 uses 'ipv8 address 0.0.0.0.*'."""
        net = Network()
        link = net.link("L12")
        r1 = Router("R1", net.trace); net.add_node(r1)
        r2 = Router("R2", net.trace); net.add_node(r2)
        r1.add_interface("Gig0/0", IPv8Address(0, 0), link)
        r2.add_interface("Gig0/0", IPv8Address(0, 0), link)
        cli1 = IOSCLI(r1); cli2 = IOSCLI(r2)
        cli1.run_script([
            "enable", "configure terminal",
            "interface Gig0/0", "ip address 10.0.0.1", "no shutdown", "exit",
            "ip route 10.0.0.0/24 interface Gig0/0",
            "end",
        ])
        # R2 configured purely with IPv8 syntax, still ASN=0
        cli2.run_script([
            "enable", "configure terminal",
            "interface Gig0/0", "ipv8 address 0.0.0.0.10.0.0.2", "no shutdown", "exit",
            "ipv8 route 0.0.0.0.10.0.0.0/24 interface Gig0/0",
            "end",
        ])
        # R1 pings using IPv4 form; R2 replies transparently
        cli1.run_script(["ping 10.0.0.2"])
        self.assertTrue(cli1.last_ping_ok,
                        msg="mixed IPv4/IPv8-native configs failed to ping")


if __name__ == "__main__":
    unittest.main()
