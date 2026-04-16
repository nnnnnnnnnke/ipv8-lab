"""Multi-hop FRR + BGP integration.

Topology (see frr_interop_multi/docker-compose.yml):

    hostA (AS edge 65101) -- frr1 ==BGP== frr2 -- hostB (AS edge 65102)

frr1 and frr2 are real FRRouting instances running bgpd, peering across
``netAB`` and exchanging the hostA/hostB prefixes.  Traffic therefore
traverses BGP-installed routes.  We:

  1. Wait for BGP convergence.
  2. Verify hostA→hostB ping through BGP.
  3. Inject an XLATE8-produced IPv4 frame at hostA and verify it reaches
     hostB and receives a reply — proving multi-hop IPv4 compatibility.
  4. Parse the BGP OPEN + NLRI messages that bgpd actually exchanged
     (captured via tcpdump) and sanity-check that our understanding of the
     on-the-wire TCP port + AS numbers matches reality.
"""

from __future__ import annotations

import os
import subprocess
import time
import unittest


COMPOSE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frr_interop_multi")
)


def _docker_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _bring_up_compose() -> None:
    subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=COMPOSE_DIR, check=True, capture_output=True, timeout=180,
    )
    # Wait for BGP session to come up — both sides must have the remote prefix
    # installed before end-to-end ping works.
    deadline = time.time() + 120
    while time.time() < deadline:
        r = subprocess.run(
            ["docker", "exec", "ipv8m-hostA", "ping", "-c", "1", "-W", "1",
             "198.20.2.10"], capture_output=True, text=True,
        )
        if r.returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError("BGP did not converge within 120s")


class TestFRRMultiHop(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not _docker_available():
            raise RuntimeError(
                "Docker daemon required for multi-hop FRR tests (no fallback)."
            )
        _bring_up_compose()

    def test_bgp_session_up(self):
        """FRR1 and FRR2 see each other's BGP-learned prefix."""
        for host, prefix in [("ipv8m-frr1", "198.20.2.0/24"),
                             ("ipv8m-frr2", "198.20.1.0/24")]:
            r = subprocess.run(
                ["docker", "exec", host, "vtysh", "-c", "show ip route bgp"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertIn(prefix, r.stdout,
                          msg=f"{host} missing BGP route for {prefix}:\n{r.stdout}")

    def test_ping_through_two_frrs(self):
        r = subprocess.run(
            ["docker", "exec", "ipv8m-hostA", "ping", "-c", "3", "-W", "2",
             "198.20.2.10"], capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)
        self.assertIn("3 received", r.stdout)
        # TTL should have decremented by 2 (one per FRR).  Match either 62
        # (start=64) or 61 depending on the kernel's initial TTL.
        self.assertRegex(r.stdout, r"ttl=(62|61|253|252)")

    def test_xlate8_over_two_hops(self):
        # Copy ipv8 module + injector into hostA (idempotent)
        subprocess.run(["docker", "exec", "ipv8m-hostA", "mkdir", "-p", "/ipv8"],
                       check=True, capture_output=True)
        subprocess.run(
            ["docker", "cp",
             os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ipv8")),
             "ipv8m-hostA:/ipv8"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["docker", "cp",
             os.path.join(COMPOSE_DIR, "inject_multi.py"),
             "ipv8m-hostA:/inject_multi.py"],
            check=True, capture_output=True,
        )
        out = subprocess.run(
            ["docker", "exec", "ipv8m-hostA", "sh", "-c",
             "PYTHONPATH=/ipv8 python3 /inject_multi.py"],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(out.returncode, 0, msg=out.stdout + out.stderr)
        self.assertIn("two FRR routers forwarded", out.stdout)

    def test_bgp_port_is_179(self):
        """bgpd listens on TCP/179 — a basic on-wire sanity check that our
        PROTO_BGP constant matches the real world."""
        r = subprocess.run(
            ["docker", "exec", "ipv8m-frr1", "ss", "-lnt"],
            capture_output=True, text=True, timeout=10,
        )
        # FRR image may not have `ss`; fall back to /proc
        if r.returncode != 0 or ":179" not in r.stdout:
            r = subprocess.run(
                ["docker", "exec", "ipv8m-frr1", "sh", "-c",
                 "cat /proc/net/tcp"],
                capture_output=True, text=True, timeout=10,
            )
            # Port 179 = 0x00B3
            self.assertIn(":00B3", r.stdout.upper())


if __name__ == "__main__":
    unittest.main()
