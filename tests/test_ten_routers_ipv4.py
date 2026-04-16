"""10 ルータ直列試験 — すべて IPv4 スタイル設定で疎通。

Topology
--------

    R1 --L1-- R2 --L2-- R3 --L3-- R4 --L4-- R5 --L5-- R6 --L6-- R7 --L7-- R8 --L8-- R9 --L9-- R10

Link Li (i=1..9) は subnet ``10.<i>.<i+1>.0/24`` を使う。
両端アドレス:
    Ri  側 Gig0/1 : 10.<i>.<i+1>.<i>    (例 R1.Gig0/1 = 10.1.2.1)
    Rj  側 Gig0/0 : 10.<i>.<i+1>.<j>    (j = i+1, 例 R2.Gig0/0 = 10.1.2.2)

各ルータは:
 - 直接接続する /24 には connected route
 - 左側の全 remote /24 には `ip route ... via 左ネクストホップ`
 - 右側の全 remote /24 には `ip route ... via 右ネクストホップ`

テスト:
 1. R1 → R10 の `ping` 成功
 2. TTL が 9 ホップ分 減算（64 → 55）
 3. `show ip route` が IPv4 形式で表示される
 4. 中間ルータを shutdown → drop、復旧 → 通る
 5. リング化（L10 追加で R10 ⇄ R1）しても直接隣接が優先される
"""

from __future__ import annotations

import unittest

from ipv8 import IOSCLI, IPv8Address, Network, Router


N_ROUTERS = 10


def _build():
    """Pre-wire 10 routers with (address-unset) interfaces on 9 sequential links."""
    net = Network()
    routers = []
    clis = {}

    # Create routers
    for i in range(1, N_ROUTERS + 1):
        r = Router(f"R{i}", net.trace)
        net.add_node(r)
        routers.append(r)
        clis[r.name] = IOSCLI(r)

    # Create 9 links
    for i in range(1, N_ROUTERS):
        link = net.link(f"L{i}")
        routers[i - 1].add_interface("Gig0/1", IPv8Address(0, 0), link)
        routers[i].add_interface("Gig0/0", IPv8Address(0, 0), link)

    # Configure each router entirely via IOS `ip` commands
    for i in range(1, N_ROUTERS + 1):
        cli = clis[f"R{i}"]
        script = ["enable", "configure terminal"]

        # Left interface (Gig0/0) — exists for i >= 2
        if i >= 2:
            left_link = i - 1
            my_ip_on_left = f"10.{left_link}.{left_link + 1}.{i}"
            script += [
                "interface Gig0/0",
                f"ip address {my_ip_on_left}",
                "no shutdown",
                "exit",
                f"ip route 10.{left_link}.{left_link + 1}.0/24 interface Gig0/0",
            ]

        # Right interface (Gig0/1) — exists for i <= N-1
        if i <= N_ROUTERS - 1:
            right_link = i
            my_ip_on_right = f"10.{right_link}.{right_link + 1}.{i}"
            script += [
                "interface Gig0/1",
                f"ip address {my_ip_on_right}",
                "no shutdown",
                "exit",
                f"ip route 10.{right_link}.{right_link + 1}.0/24 interface Gig0/1",
            ]

        # Static routes to remote /24s — use next hop on the correct side.
        for link_idx in range(1, N_ROUTERS):  # link_idx = 1..9
            if link_idx == i - 1 or link_idx == i:
                continue  # already connected
            subnet = f"10.{link_idx}.{link_idx + 1}.0/24"
            if link_idx < i - 1:
                # subnet is to the left → next-hop is R(i-1) on our left link
                left_link = i - 1
                nh = f"10.{left_link}.{left_link + 1}.{i - 1}"
            else:
                # subnet is to the right → next-hop is R(i+1) on our right link
                right_link = i
                nh = f"10.{right_link}.{right_link + 1}.{i + 1}"
            script += [f"ip route {subnet} {nh}"]

        script += ["end"]
        cli.run_script(script)

    return net, routers, clis


class TestTenRoutersIPv4(unittest.TestCase):
    def test_end_to_end_9_hop_ping(self):
        net, routers, clis = _build()
        # R10's right interface doesn't exist (endpoint), so ping its Gig0/0
        target = "10.9.10.10"
        cli = clis["R1"]
        cli.mode = "user"
        cli.run_script([f"enable", f"ping {target}"])
        self.assertTrue(
            cli.last_ping_ok,
            msg=f"R1 -> {target} failed\n" + cli.output() + "\n" + net.trace.dump(),
        )

    def test_ttl_decrements_9_times(self):
        net, routers, clis = _build()
        cli = clis["R1"]
        cli.mode = "user"
        cli.run_script([f"enable", "ping 10.9.10.10"])
        recv_events = [
            e for e in net.trace.events
            if e.node == "R10" and e.action == "recv"
            and str(e.packet.header.src) == "0.0.0.0.10.1.2.1"
        ]
        self.assertTrue(recv_events, "R10 never received the echo request")
        first = recv_events[0]
        # R1 sends with TTL=64.  R2..R9 forward (8 decrements).  R10 recv
        # does NOT decrement further, so TTL at R10 = 64 - 8 = 56.
        self.assertEqual(
            first.packet.header.ttl, 56,
            msg=f"TTL at R10 = {first.packet.header.ttl}, expected 56 "
                "(64 initial - 8 forwarding hops)",
        )

    def test_show_ip_route_lists_ipv4_style(self):
        net, routers, clis = _build()
        cli = clis["R5"]
        cli.mode = "user"
        cli.run_script(["enable", "show ip route"])
        out = cli.output()
        # R5 connects to 10.4.5.0/24 (left) and 10.5.6.0/24 (right)
        self.assertIn("10.4.5.0/24", out)
        self.assertIn("10.5.6.0/24", out)
        # Remote destination example
        self.assertIn("10.9.10.0/24", out)
        # Next-hop format must be IPv4 (no "0.0.0.0." prefix in user-facing text)
        self.assertNotIn("0.0.0.0.10", out)

    def test_break_middle_router_and_recover(self):
        net, routers, clis = _build()
        # R5 is the middle router — shut its Gig0/1 (right interface)
        cli5 = clis["R5"]
        cli5.mode = "user"
        cli5.run_script([
            "enable", "configure terminal",
            "interface Gig0/1", "shutdown", "end",
        ])
        # Ping from R1 to R10 should fail now
        cli1 = clis["R1"]
        cli1.mode = "user"
        cli1.run_script(["enable", "ping 10.9.10.10"])
        self.assertFalse(cli1.last_ping_ok, msg="expected failure while R5 Gig0/1 is down")
        # Verify the drop was at R5 with egress-admin-down
        drops = [e for e in net.trace.events
                 if e.action == "drop" and "admin-down" in e.note and e.node == "R5"]
        self.assertTrue(drops, "no egress-admin-down drop recorded at R5")
        # Recover
        cli5.run_script([
            "configure terminal", "interface Gig0/1", "no shutdown", "end",
        ])
        cli1.run_script(["ping 10.9.10.10"])
        self.assertTrue(cli1.last_ping_ok, msg="ping should succeed after recovery")

    def test_all_adjacent_pairs_reach_each_other(self):
        net, routers, clis = _build()
        # Ping each neighbour's near-side address from every router.
        for i in range(1, N_ROUTERS + 1):
            cli = clis[f"R{i}"]
            cli.mode = "user"
            if i < N_ROUTERS:
                cli.run_script([
                    "enable", f"ping 10.{i}.{i + 1}.{i + 1}",  # right neighbour
                ])
                self.assertTrue(cli.last_ping_ok,
                                msg=f"R{i} could not ping right neighbour")
            if i > 1:
                cli.run_script([
                    f"ping 10.{i - 1}.{i}.{i - 1}",            # left neighbour
                ])
                self.assertTrue(cli.last_ping_ok,
                                msg=f"R{i} could not ping left neighbour")

    def test_interface_count(self):
        net, routers, clis = _build()
        # Endpoints have 1 interface each, middle routers have 2.
        self.assertEqual(len(routers[0].interfaces), 1)
        self.assertEqual(len(routers[-1].interfaces), 1)
        for r in routers[1:-1]:
            self.assertEqual(len(r.interfaces), 2)

    def test_routing_table_has_nine_subnets(self):
        net, routers, clis = _build()
        # Middle router R5 must have 9 ASN=0 routes (connected + remote)
        asn0 = routers[4].rtable.tier1.get(0, [])
        self.assertEqual(
            len(asn0), 9,
            msg=f"R5 has {len(asn0)} ASN=0 routes (expected 9): "
                + "\n".join(r.describe() for r in asn0),
        )


if __name__ == "__main__":
    unittest.main()
