#!/usr/bin/env python3
"""Stdlib pack/parse tests for scan_erv.py. No network."""

from __future__ import annotations

import struct
import unittest

import scan_erv as m


class PackMbapTests(unittest.TestCase):
    def test_pack_mbap_length_includes_unit_and_pdu(self) -> None:
        pdu = b"\x03\x00\x01\x00\x03"
        frame = m.pack_mbap(1, 2, pdu)
        tid, proto, length, unit = struct.unpack(">HHHB", frame[:7])
        self.assertEqual(tid, 1)
        self.assertEqual(proto, 0)
        self.assertEqual(length, 1 + len(pdu))
        self.assertEqual(unit, 2)
        self.assertEqual(frame[7:], pdu)


class ReadHoldingTests(unittest.TestCase):
    def test_pack_matches_legacy_struct(self) -> None:
        packed = m.pack_read_holding(slave=2, address=1, count=3, transaction_id=1)
        legacy = struct.pack(">HHHBBHH", 1, 0, 6, 2, 3, 1, 3)
        self.assertEqual(packed, legacy)
        self.assertEqual(packed, bytes.fromhex("0001 0000 0006 02 03 0001 0003"))

    def test_parse_three_registers(self) -> None:
        resp = bytes.fromhex("0001 0000 0009 02 03 06 0001 0000 0003")
        self.assertEqual(m.parse_read_holding(resp, slave=2, count=3), [1, 0, 3])

    def test_parse_rejects_wrong_slave(self) -> None:
        resp = bytes.fromhex("0001 0000 0009 01 03 06 0001 0000 0003")
        self.assertIsNone(m.parse_read_holding(resp, slave=2, count=3))

    def test_parse_rejects_exception(self) -> None:
        resp = bytes.fromhex("0001 0000 0003 02 83 02")
        self.assertIsNone(m.parse_read_holding(resp, slave=2, count=3))

    def test_parse_rejects_truncated(self) -> None:
        self.assertIsNone(m.parse_read_holding(b"\x00\x01", slave=2, count=3))
        resp = bytes.fromhex("0001 0000 0009 02 03 06 0001 0000")
        self.assertIsNone(m.parse_read_holding(resp, slave=2, count=3))

    def test_parse_rejects_wrong_byte_count(self) -> None:
        resp = bytes.fromhex("0001 0000 0007 02 03 04 0001 0000")
        self.assertIsNone(m.parse_read_holding(resp, slave=2, count=3))


class WriteSingleFc06Tests(unittest.TestCase):
    def test_pack_request(self) -> None:
        packed = m.pack_write_single(slave=2, address=1, value=0, transaction_id=1)
        self.assertEqual(packed[7], 6)
        self.assertEqual(packed, bytes.fromhex("0001 0000 0006 02 06 0001 0000"))

    def test_parse_echo(self) -> None:
        echo = bytes.fromhex("0001 0000 0006 02 06 0001 0001")
        self.assertTrue(m.parse_write_single(echo, slave=2, address=1, value=1))

    def test_parse_rejects_wrong_value(self) -> None:
        echo = bytes.fromhex("0001 0000 0006 02 06 0001 0000")
        self.assertFalse(m.parse_write_single(echo, slave=2, address=1, value=1))

    def test_parse_rejects_wrong_slave(self) -> None:
        echo = bytes.fromhex("0001 0000 0006 02 06 0001 0001")
        self.assertFalse(m.parse_write_single(echo, slave=3, address=1, value=1))

    def test_parse_rejects_exception(self) -> None:
        resp = bytes.fromhex("0001 0000 0003 02 86 01")
        self.assertFalse(m.parse_write_single(resp, slave=2, address=1, value=1))


class WriteMultipleFc16Tests(unittest.TestCase):
    def test_pack_one_register(self) -> None:
        packed = m.pack_write_multiple(slave=2, address=1, values=[1], transaction_id=1)
        self.assertEqual(packed[7], 16)
        self.assertEqual(
            packed,
            bytes.fromhex("0001 0000 0009 02 10 0001 0001 02 0001"),
        )

    def test_pack_two_registers(self) -> None:
        packed = m.pack_write_multiple(slave=2, address=2, values=[0, 3], transaction_id=7)
        self.assertEqual(
            packed,
            bytes.fromhex("0007 0000 000b 02 10 0002 0002 04 0000 0003"),
        )

    def test_parse_echo(self) -> None:
        resp = bytes.fromhex("0001 0000 0006 02 10 0001 0001")
        self.assertTrue(m.parse_write_multiple(resp, slave=2, address=1, count=1))

    def test_parse_rejects_wrong_slave(self) -> None:
        resp = bytes.fromhex("0001 0000 0006 02 10 0001 0001")
        self.assertFalse(m.parse_write_multiple(resp, slave=3, address=1, count=1))

    def test_parse_rejects_wrong_count(self) -> None:
        resp = bytes.fromhex("0001 0000 0006 02 10 0001 0002")
        self.assertFalse(m.parse_write_multiple(resp, slave=2, address=1, count=1))

    def test_parse_rejects_exception(self) -> None:
        resp = bytes.fromhex("0001 0000 0003 02 90 01")
        self.assertFalse(m.parse_write_multiple(resp, slave=2, address=1, count=1))

    def test_empty_values_raises(self) -> None:
        with self.assertRaises(ValueError):
            m.pack_write_multiple(slave=2, address=1, values=[])


class CliGuardTests(unittest.TestCase):
    def test_default_scan_is_not_a_write(self) -> None:
        args = m.parse_args([])
        self.assertIsNone(args.power)
        self.assertFalse(args.read)

    def test_power_requires_slave(self) -> None:
        self.assertEqual(m.main(["--power", "on"]), 2)

    def test_read_requires_slave(self) -> None:
        self.assertEqual(m.main(["--read"]), 2)

    def test_slave_alone_is_not_a_write(self) -> None:
        self.assertEqual(m.main(["--slave", "2"]), 2)


if __name__ == "__main__":
    unittest.main()
