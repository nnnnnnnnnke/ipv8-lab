"""Demo 5 — five routers, pure Cisco-style CLI configuration.

Same topology as tests/test_five_routers.py but run as a script so you can
watch the whole thing happen: configuration, show commands, and ping8.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_five_routers import TestFiveRouters


def main() -> None:
    t = TestFiveRouters()
    net, hA, hB, routers, clis = t.build()

    print("========== running-config on R3 ==========")
    print(clis["R3"]._running_config())

    print("\n========== show ipv8 route on R3 ==========")
    c = clis["R3"]
    c.run_script(["show ipv8 route"])
    print(c.output().splitlines()[-15:])

    print("\n========== ping8 R1 -> R5 ==========")
    r5 = routers[4].interfaces["Gig0/1"].address
    clis["R1"].run_script([f"ping8 {r5}"])
    print("\n".join(clis["R1"].output().splitlines()[-6:]))

    print("\n========== host-to-host ping trace (hostA -> hostB) ==========")
    before = len(net.trace.events)
    hA.ping(hB.address, identifier=0xDEAD, sequence=1)
    net.step()
    print(net.trace.dump())
    print(f"\nreplies at hostA: {hA.ping_replies}")


if __name__ == "__main__":
    main()
