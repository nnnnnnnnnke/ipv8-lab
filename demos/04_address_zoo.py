"""Demo 4 — address classification zoo.

Walks every reserved / special address class defined in the draft and
prints how the library classifies it.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipv8 import IPv8Address


EXAMPLES = [
    ("0.0.251.240.192.168.1.10",   "ASN 64496 global unicast"),
    ("0.0.0.0.8.8.8.8",            "IPv4-compat (Google DNS)"),
    ("127.0.0.0.10.1.2.3",         "Internal-zone prefix"),
    ("127.127.0.0.10.1.2.3",       "Inter-company DMZ"),
    ("100.1.2.3.10.0.0.1",         "RINE peering link"),
    ("0.0.255.253.198.51.100.1",   "Documentation ASN (65533)"),
    ("255.255.255.255.255.255.255.255", "Global broadcast"),
    ("255.255.0.1.0.0.0.0",        "OSPF8 multicast group"),
    ("255.255.0.0.224.0.0.1",      "All-IPv8-Routers multicast"),
    ("255.255.0.0.224.0.0.2",      "All-IPv8-Zone-Servers multicast"),
]


def main() -> None:
    print(f"{'ADDRESS':<40s} {'CLASS':<16s} {'ROUTABLE':<9s} NOTE")
    print("-" * 100)
    for s, note in EXAMPLES:
        a = IPv8Address.from_string(s)
        print(f"{str(a):<40s} {a.classify():<16s} {str(a.is_routable()):<9s} {note}")


if __name__ == "__main__":
    main()
