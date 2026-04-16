"""Adversarial CLI tests — every malformed command must be rejected cleanly."""

from __future__ import annotations

import unittest

from ipv8 import IOSCLI, IPv8Address, Network, Router

from tests.helpers import addr


def _fresh_router() -> tuple[Router, IOSCLI]:
    net = Network()
    link = net.link("L")
    r = Router("R", net.trace)
    r.add_interface("Gig0/0", addr(65001, "10.0.0.1"), link)
    net.add_node(r)
    return r, IOSCLI(r)


class TestCLINegative(unittest.TestCase):
    def test_unknown_command_in_user_mode(self):
        r, cli = _fresh_router()
        cli.run_script(["banana"])
        self.assertIn("Invalid input", cli.output())

    def test_configure_without_terminal_arg(self):
        r, cli = _fresh_router()
        cli.run_script(["enable", "configure"])
        self.assertIn("usage: configure terminal", cli.output())

    def test_interface_missing_name(self):
        r, cli = _fresh_router()
        cli.run_script(["enable", "configure terminal", "interface"])
        self.assertIn("usage: interface NAME", cli.output())

    def test_interface_nonexistent(self):
        r, cli = _fresh_router()
        cli.run_script(["enable", "configure terminal", "interface no-such-iface"])
        self.assertIn("no such interface", cli.output())

    def test_ipv8_address_bad_format(self):
        r, cli = _fresh_router()
        cli.run_script([
            "enable", "configure terminal", "interface Gig0/0",
            "ipv8 address not.an.address",
        ])
        self.assertTrue(
            "octet" in cli.output() or "8 dotted octets" in cli.output(),
            msg=cli.output(),
        )

    def test_ipv8_address_octet_out_of_range(self):
        r, cli = _fresh_router()
        cli.run_script([
            "enable", "configure terminal", "interface Gig0/0",
            "ipv8 address 0.0.0.0.0.0.0.999",
        ])
        self.assertIn("octet out of range", cli.output())

    def test_route_prefix_without_slash(self):
        r, cli = _fresh_router()
        cli.run_script([
            "enable", "configure terminal",
            "ipv8 route 0.0.0.1.10.0.0.0 0.0.0.1.10.0.0.2",
        ])
        self.assertIn("prefix must be ADDR/LEN", cli.output())

    def test_route_prefix_len_out_of_range(self):
        r, cli = _fresh_router()
        cli.run_script([
            "enable", "configure terminal",
            "ipv8 route 0.0.0.1.10.0.0.0/99 0.0.0.1.10.0.0.2",
        ])
        self.assertIn("host prefix length", cli.output())

    def test_route_interface_missing(self):
        r, cli = _fresh_router()
        cli.run_script([
            "enable", "configure terminal",
            "ipv8 route 0.0.0.1.10.0.0.0/24 interface bogus",
        ])
        self.assertIn("no such interface", cli.output())

    def test_route_next_hop_unresolvable(self):
        r, cli = _fresh_router()
        # interface Gig0/0 is in ASN 65001.  Next-hop in ASN 64999 → unresolvable.
        cli.run_script([
            "enable", "configure terminal",
            "ipv8 route 0.0.253.247.10.0.0.0/24 0.0.253.247.10.99.0.1",
        ])
        self.assertIn("cannot resolve egress interface", cli.output())

    def test_no_ipv8_route_without_args(self):
        r, cli = _fresh_router()
        cli.run_script(["enable", "configure terminal", "no ipv8 route"])
        self.assertIn("usage: no ipv8 route", cli.output())

    def test_no_ipv8_route_removes_entry(self):
        r, cli = _fresh_router()
        cli.run_script([
            "enable", "configure terminal",
            "interface Gig0/0", "ipv8 address 0.0.253.233.10.0.0.1", "no shutdown", "exit",
            "ipv8 route 0.0.253.234.0.0.0.0/0 0.0.253.233.10.0.0.2",
        ])
        self.assertIn(65002, r.rtable.tier1)
        cli.run_script([
            "configure terminal",
            "no ipv8 route 0.0.253.234.0.0.0.0/0",
            "end",
        ])
        self.assertNotIn(65002, r.rtable.tier1)

    def test_ping8_without_target(self):
        r, cli = _fresh_router()
        cli.run_script(["enable", "ping8"])
        self.assertIn("usage: ping8 ADDR", cli.output())

    def test_ping8_bad_address(self):
        r, cli = _fresh_router()
        cli.run_script(["enable", "ping8 garbage"])
        self.assertTrue(
            "8 dotted octets" in cli.output() or "octet" in cli.output(),
        )

    def test_show_unknown_subcommand(self):
        r, cli = _fresh_router()
        cli.run_script(["enable", "show something"])
        self.assertIn("usage: show", cli.output())

    def test_conflicting_interface_reassignment(self):
        """Readdressing an interface must work; subsequent address sticks."""
        r, cli = _fresh_router()
        cli.run_script([
            "enable", "configure terminal",
            "interface Gig0/0",
            "ipv8 address 0.0.253.233.10.0.0.1",
            "ipv8 address 0.0.253.233.10.0.0.9",
        ])
        self.assertEqual(
            r.interfaces["Gig0/0"].address,
            IPv8Address.from_string("0.0.253.233.10.0.0.9"),
        )

    def test_history_records_all_lines(self):
        r, cli = _fresh_router()
        cli.run_script(["enable", "configure terminal", "interface Gig0/0"])
        self.assertEqual(
            cli.history, ["enable", "configure terminal", "interface Gig0/0"]
        )


if __name__ == "__main__":
    unittest.main()
