"""Demo 2 — cross-AS ICMPv8 echo across two border routers.

Topology:

    hostA (AS 64496, 192.168.1.10)
      |
     [linkA]
      |
     R1 -- [linkCore] -- R2
                           |
                          [linkB]
                           |
                    hostB (AS 64497, 10.0.0.5)

R1 holds AS64496 internal routes + default to R2.
R2 holds AS64497 internal routes + default to R1.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipv8 import Host, IPv8Address, Network, Route, Router


def main() -> None:
    net = Network()
    linkA = net.link("linkA")
    linkCore = net.link("linkCore")
    linkB = net.link("linkB")

    addr_A = IPv8Address.from_asn_and_ipv4(64496, "192.168.1.10")
    addr_B = IPv8Address.from_asn_and_ipv4(64497, "10.0.0.5")
    addr_R1a = IPv8Address.from_asn_and_ipv4(64496, "192.168.1.1")
    addr_R1c = IPv8Address.from_asn_and_ipv4(64496, "222.0.0.1")
    addr_R2c = IPv8Address.from_asn_and_ipv4(64497, "222.0.0.2")
    addr_R2b = IPv8Address.from_asn_and_ipv4(64497, "10.0.0.1")

    hA = Host("hostA", addr_A, net.trace); hA.add_interface("eth0", addr_A, linkA); hA.gateway_iface = "eth0"
    hB = Host("hostB", addr_B, net.trace); hB.add_interface("eth0", addr_B, linkB); hB.gateway_iface = "eth0"

    R1 = Router("R1", net.trace)
    R1.add_interface("ethA", addr_R1a, linkA)
    R1.add_interface("ethCore", addr_R1c, linkCore)
    R1.rtable.add(Route(64496, 0xC0A80100, 24, None, "ethA"))
    R1.rtable.add(Route(64497, 0, 0, addr_R2c, "ethCore"))

    R2 = Router("R2", net.trace)
    R2.add_interface("ethCore", addr_R2c, linkCore)
    R2.add_interface("ethB", addr_R2b, linkB)
    R2.rtable.add(Route(64497, 0x0A000000, 8, None, "ethB"))
    R2.rtable.add(Route(64496, 0, 0, addr_R1c, "ethCore"))

    for n in (hA, hB, R1, R2):
        net.add_node(n)

    print("=== Routing tables ===")
    print("R1:"); print(R1.rtable.dump())
    print(); print("R2:"); print(R2.rtable.dump())

    print()
    print("=== hostA pings hostB (echo request id=42 seq=1) ===")
    hA.ping(hB.address, identifier=42, sequence=1)
    net.step()

    print()
    print("=== Packet trace ===")
    print(net.trace.dump())
    print()
    print(f"hostA received replies: {hA.ping_replies}")


if __name__ == "__main__":
    main()
