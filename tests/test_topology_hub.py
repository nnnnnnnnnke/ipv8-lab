"""Hub-and-spoke topology (1 hub router, 6 hosts).

Every host lives on its own /24 connected to the hub.  This exercises host
density and proves one Tier-1 bucket (ASN 65300) can hold 6 distinct
longest-prefix entries at Tier 2.
"""

import unittest

from ipv8 import Network

from tests.helpers import RouterBuilder, addr


HUB_ASN = 65300


def _build():
    net = Network()
    b = RouterBuilder(net)
    hub = b.router("Hub")
    hosts = {}
    for i in range(1, 7):
        link = net.link(f"hlink{i}")
        iface = f"Gi0/{i - 1}"
        b.attach(hub, iface, addr(HUB_ASN, f"10.{i}.0.1"), link)
        b.add_connected(
            hub, HUB_ASN,
            int.from_bytes(bytes([10, i, 0, 0]), "big"),
            24, iface,
        )
        hosts[f"h{i}"] = b.host(f"h{i}", addr(HUB_ASN, f"10.{i}.0.10"), link)
    return net, b, hosts


class TestHubAndSpoke(unittest.TestCase):
    def test_every_host_reachable(self):
        net, b, hosts = _build()
        src = hosts["h1"]
        for name, dst in hosts.items():
            if name == "h1":
                continue
            src.ping_replies.clear()
            src.ping(dst.address, identifier=int(name[1:]), sequence=1)
            net.step()
            self.assertIn((int(name[1:]), 1), src.ping_replies,
                          msg=f"h1 -> {name} failed\n" + net.trace.dump())

    def test_hub_routing_table_has_six_connected(self):
        net, b, hosts = _build()
        # 6 /24 connected routes under the single hub ASN
        self.assertEqual(len(b.routers["Hub"].rtable.tier1[HUB_ASN]), 6)


if __name__ == "__main__":
    unittest.main()
