import unittest

from ipv8.icmp import (
    ICMPv8Message,
    TYPE_ECHO_REPLY,
    TYPE_ECHO_REQUEST,
    echo_reply,
    echo_request,
)


class TestICMP(unittest.TestCase):
    def test_echo_request_roundtrip(self):
        buf = echo_request(identifier=0x1234, sequence=7, payload=b"ping")
        msg = ICMPv8Message.from_bytes(buf)
        self.assertEqual(msg.icmp_type, TYPE_ECHO_REQUEST)
        self.assertEqual(msg.identifier, 0x1234)
        self.assertEqual(msg.sequence, 7)
        self.assertEqual(msg.data, b"ping")

    def test_echo_reply_roundtrip(self):
        buf = echo_reply(identifier=1, sequence=1, payload=b"")
        msg = ICMPv8Message.from_bytes(buf)
        self.assertEqual(msg.icmp_type, TYPE_ECHO_REPLY)

    def test_bad_checksum(self):
        buf = bytearray(echo_request(1, 1, b"abc"))
        buf[2] ^= 0xFF  # corrupt the checksum field itself
        with self.assertRaises(ValueError):
            ICMPv8Message.from_bytes(bytes(buf))


if __name__ == "__main__":
    unittest.main()
