"""Test the Cisco-style CLI drives a single router correctly."""

import unittest

from ipv8 import IPv8Address, IOSCLI, Network, Router


def make_router(name: str) -> Router:
    net = Network()
    link = net.link("L")
    r = Router(name, net.trace)
    placeholder = IPv8Address.from_asn_and_ipv4(64500, "10.0.0.1")
    r.add_interface("GigabitEthernet0/0", placeholder, link)
    net.add_node(r)
    return r


class TestIOS(unittest.TestCase):
    def test_mode_transitions(self):
        r = make_router("R0")
        cli = IOSCLI(r)
        cli.run_script(["enable", "configure terminal"])
        self.assertEqual(cli.mode, "conf")
        cli.run_script(["interface GigabitEthernet0/0"])
        self.assertEqual(cli.mode, "conf-if")
        self.assertEqual(cli.current_iface, "GigabitEthernet0/0")
        cli.run_script(["end"])
        self.assertEqual(cli.mode, "priv")
        self.assertIsNone(cli.current_iface)

    def test_ipv8_address_and_route(self):
        r = make_router("R0")
        cli = IOSCLI(r)
        cli.run_script([
            "enable",
            "configure terminal",
            "hostname Core1",
            "interface GigabitEthernet0/0",
            "ipv8 address 0.0.251.240.10.1.0.1",
            "no shutdown",
            "exit",
            "ipv8 route 0.0.251.241.10.2.0.0/16 0.0.251.240.10.1.0.2",
            "end",
            "show ipv8 route",
        ])
        self.assertEqual(r.name, "Core1")
        self.assertEqual(
            r.interfaces["GigabitEthernet0/0"].address,
            IPv8Address.from_string("0.0.251.240.10.1.0.1"),
        )
        self.assertEqual(len(r.rtable.tier1.get(64497, [])), 1)
        out = cli.output()
        self.assertIn("10.2.0.0/16", out)
        self.assertIn("Core1", out)  # prompt should include new hostname

    def test_invalid_command(self):
        r = make_router("R0")
        cli = IOSCLI(r)
        cli.run_script(["enable", "configure terminal", "bogus command"])
        self.assertIn("Invalid input", cli.output())

    def test_running_config_roundtrip(self):
        r = make_router("R0")
        cli = IOSCLI(r)
        cli.run_script([
            "enable",
            "configure terminal",
            "hostname X",
            "interface GigabitEthernet0/0",
            "ipv8 address 0.0.0.1.10.0.0.1",
            "no shutdown",
            "end",
            "show running-config",
        ])
        out = cli.output()
        self.assertIn("hostname X", out)
        self.assertIn("interface GigabitEthernet0/0", out)
        self.assertIn("ipv8 address 0.0.0.1.10.0.0.1", out)
        self.assertIn("no shutdown", out)


if __name__ == "__main__":
    unittest.main()
