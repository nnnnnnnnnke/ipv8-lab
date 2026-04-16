"""Constants defined by draft-thain-ipv8-00."""

IP_VERSION = 8
HEADER_LEN = 40
IHL = 10  # header length in 32-bit words (40 / 4)

# Well-known ASNs
ASN_PRIVATE_BGP = 65534
ASN_DOCUMENTATION = 65533

# Protocol numbers (IANA, reused from IPv4)
PROTO_ICMP = 1
PROTO_ICMPV8 = 58  # Draft does not fix a number; reuse ICMPv6's value for the lab
PROTO_TCP = 6
PROTO_UDP = 17
PROTO_OSPF = 89
PROTO_BGP = 179  # layered on TCP in reality; used as a marker in the sim

# Address well-known patterns (as tuples of 8 octets)
BROADCAST_PREFIX = (0xFF, 0xFF, 0xFF, 0xFF)
INTERNAL_ZONE_PREFIX_FIRST = 127
RINE_PEERING_PREFIX_FIRST = 100
DMZ_PREFIX = (127, 127, 0, 0)
DOCUMENTATION_PREFIX = (0, 0, 255, 253)

# Multicast groups (r.r.r.r portion starts with ff.ff)
MCAST_PREFIX = (0xFF, 0xFF)
MCAST_OSPF8 = (0xFF, 0xFF, 0x00, 0x01)
MCAST_BGP8 = (0xFF, 0xFF, 0x00, 0x02)
MCAST_ISIS8 = (0xFF, 0xFF, 0x00, 0x05)
MCAST_ALL_ROUTERS_SUFFIX = (224, 0, 0, 1)
MCAST_ALL_ZONE_SERVERS_SUFFIX = (224, 0, 0, 2)

# PVRST
PVRST_ROOT_PRIORITY = 4096

# NIC rate limits
RATE_UNAUTH_PER_SEC = 10
RATE_UNAUTH_PER_MIN = 30
RATE_AUTH_PER_SEC = 100
RATE_AUTH_PER_MIN = 300

# Interior link convention "any-asn.222.x.x.x" — host-side starts with 222
INTERIOR_LINK_HOST_FIRST = 222

# AF family numeric (made-up, not IANA)
AF_INET8 = 28
