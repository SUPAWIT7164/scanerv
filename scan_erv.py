#!/usr/bin/env python3
"""Scan ERV Modbus slaves behind HF5111SC, and optionally read/write Power.

Stop the Home Assistant ERV hub first. This gateway usually allows
only one TCP client at a time.

Default (no flags) only scans slaves 1-16. It never writes registers.

Holding registers 1-3 = Power / Mode / Air
  power: 0=off 1=on
  mode:  0=Heat-Exchange 1=Normal
  air:   1=Low 3=High

Examples (stop HA first):
  python3 scan_erv.py
  python3 scan_erv.py --slave 2 --read
  python3 scan_erv.py --slave 2 --power on
  python3 scan_erv.py --slave 2 --power off
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time

HOST = "172.17.24.160"
PORT = 8899
SLAVE_START = 1
SLAVE_END = 16
REG_START = 1
REG_COUNT = 3
POWER_REG = 1
TIMEOUT_SEC = 1.5
GAP_SEC = 0.2
WRITE_READBACK_SEC = 0.4

FC_READ_HOLDING = 3
FC_WRITE_SINGLE = 6  # FC06
FC_WRITE_MULTIPLE = 16  # FC16

HA_SINGLE_CLIENT_MSG = (
    "Stop the Home Assistant ERV hub first. This gateway is single-client; "
    "HA and this script cannot share 172.17.24.160:8899."
)


def pack_mbap(transaction_id: int, unit: int, pdu: bytes) -> bytes:
    """Build a Modbus TCP ADU: MBAP header + unit id + PDU."""
    length = 1 + len(pdu)  # unit id + PDU
    return struct.pack(">HHHB", transaction_id, 0, length, unit) + pdu


def parse_mbap(data: bytes) -> tuple[int, int, bytes] | None:
    """Return (transaction_id, unit, pdu) or None if the header is truncated."""
    if len(data) < 8:
        return None
    tid, proto, length, unit = struct.unpack(">HHHB", data[:7])
    if proto != 0 or length < 1:
        return None
    pdu = data[7:]
    if len(pdu) < length - 1:
        return None
    return tid, unit, pdu[: length - 1]


def pack_read_holding(
    slave: int, address: int, count: int, transaction_id: int = 1
) -> bytes:
    """FC03 Read Holding Registers request."""
    pdu = struct.pack(">BHH", FC_READ_HOLDING, address, count)
    return pack_mbap(transaction_id, slave, pdu)


def parse_read_holding(data: bytes, slave: int, count: int) -> list[int] | None:
    """Parse an FC03 response into register values, or None on error."""
    parsed = parse_mbap(data)
    if parsed is None:
        return None
    _, unit, pdu = parsed
    if unit != slave or len(pdu) < 2:
        return None
    func, byte_count = pdu[0], pdu[1]
    if func != FC_READ_HOLDING:
        return None
    if byte_count != count * 2 or len(pdu) < 2 + byte_count:
        return None
    values = []
    raw = pdu[2 : 2 + byte_count]
    for i in range(count):
        values.append(struct.unpack(">H", raw[i * 2 : i * 2 + 2])[0])
    return values


def pack_write_single(
    slave: int, address: int, value: int, transaction_id: int = 1
) -> bytes:
    """FC06 Write Single Register request."""
    pdu = struct.pack(">BHH", FC_WRITE_SINGLE, address, value & 0xFFFF)
    return pack_mbap(transaction_id, slave, pdu)


def parse_write_single(data: bytes, slave: int, address: int, value: int) -> bool:
    """True if the FC06 response echoes address and value."""
    parsed = parse_mbap(data)
    if parsed is None:
        return False
    _, unit, pdu = parsed
    if unit != slave or len(pdu) < 5:
        return False
    func, resp_addr, resp_value = struct.unpack(">BHH", pdu[:5])
    return (
        func == FC_WRITE_SINGLE
        and resp_addr == address
        and resp_value == (value & 0xFFFF)
    )


def pack_write_multiple(
    slave: int, address: int, values: list[int], transaction_id: int = 1
) -> bytes:
    """FC16 Write Multiple Registers request."""
    count = len(values)
    if count < 1:
        raise ValueError("FC16 requires at least one register")
    byte_count = count * 2
    pdu = struct.pack(">BHHB", FC_WRITE_MULTIPLE, address, count, byte_count)
    pdu += b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
    return pack_mbap(transaction_id, slave, pdu)


def parse_write_multiple(data: bytes, slave: int, address: int, count: int) -> bool:
    """True if the FC16 response echoes start address and quantity."""
    parsed = parse_mbap(data)
    if parsed is None:
        return False
    _, unit, pdu = parsed
    if unit != slave or len(pdu) < 5:
        return False
    func, resp_addr, resp_count = struct.unpack(">BHH", pdu[:5])
    return (
        func == FC_WRITE_MULTIPLE
        and resp_addr == address
        and resp_count == count
    )


def transact(host: str, port: int, request: bytes) -> bytes:
    with socket.create_connection((host, port), timeout=TIMEOUT_SEC) as sock:
        sock.settimeout(TIMEOUT_SEC)
        sock.sendall(request)
        return sock.recv(256)


def read_holding(
    host: str, port: int, slave: int, address: int, count: int
) -> list[int] | None:
    req = pack_read_holding(slave, address, count)
    try:
        data = transact(host, port, req)
    except OSError:
        return None
    return parse_read_holding(data, slave, count)


def write_holding_fc16(host: str, port: int, slave: int, address: int, value: int) -> bool:
    req = pack_write_multiple(slave, address, [value])
    try:
        data = transact(host, port, req)
    except OSError:
        return False
    return parse_write_multiple(data, slave, address, 1)


def write_holding_fc06(host: str, port: int, slave: int, address: int, value: int) -> bool:
    req = pack_write_single(slave, address, value)
    try:
        data = transact(host, port, req)
    except OSError:
        return False
    return parse_write_single(data, slave, address, value)


def decode(power: int, mode: int, air: int) -> str:
    mode_txt = {0: "Heat-Exchange", 1: "Normal"}.get(mode, f"raw {mode}")
    air_txt = {1: "Low", 3: "High"}.get(air, f"raw {air}")
    return f"power={power}  mode={mode} ({mode_txt})  air={air} ({air_txt})"


def format_values(values: list[int] | None, slave: int) -> str:
    if values is None:
        return f"slave {slave:>2}: no response"
    return f"slave {slave:>2}: OK   {decode(*values)}"


def scan(host: str, port: int) -> list[int]:
    print(f"Scanning {host}:{port} slaves {SLAVE_START}-{SLAVE_END}")
    print("Read holding registers 1-3 = Power / Mode / Air")
    print("Scan never writes. Close Home Assistant ERV connection before scanning.\n")
    print(HA_SINGLE_CLIENT_MSG, "\n", sep="")

    found: list[int] = []
    for slave in range(SLAVE_START, SLAVE_END + 1):
        try:
            values = read_holding(host, port, slave, REG_START, REG_COUNT)
        except OSError:
            values = None

        if values is None:
            print(f"slave {slave:>2}: no response")
        else:
            found.append(slave)
            print(format_values(values, slave))

        time.sleep(GAP_SEC)

    print()
    if found:
        print("Found slaves:", ", ".join(str(n) for n in found))
        print("Put these numbers into modbus.yaml as slave: for U1-U4")
    else:
        print(
            "No slave answered. Check DIP, ERV power, RS485 A/B, "
            "and that HA is disconnected."
        )
    return found


def read_slave(host: str, port: int, slave: int) -> list[int] | None:
    print(HA_SINGLE_CLIENT_MSG)
    print(f"Reading {host}:{port} slave {slave} holding {REG_START}-{REG_START + REG_COUNT - 1}")
    values = read_holding(host, port, slave, REG_START, REG_COUNT)
    print(format_values(values, slave))
    return values


def set_power(host: str, port: int, slave: int, on: bool) -> int:
    """Write Power (reg 1). Try FC16 first, then FC06 if the register did not change.

    Returns 0 on success, 1 on failure. Never called from a normal scan.
    """
    target = 1 if on else 0
    print(HA_SINGLE_CLIENT_MSG)
    print(
        f"Set Power {'ON' if on else 'OFF'} on {host}:{port} slave {slave} "
        f"holding address {POWER_REG} (value {target})"
    )

    before = read_holding(host, port, slave, REG_START, REG_COUNT)
    print("before:", format_values(before, slave))
    if before is not None and before[0] == target:
        print(f"Already at power={target}; no write needed.")
        return 0

    print("Write FC16 (write multiple registers) first — many HVAC units reject FC06.")
    fc16_ok = write_holding_fc16(host, port, slave, POWER_REG, target)
    print(f"FC16 response: {'ok' if fc16_ok else 'no/invalid response'}")
    time.sleep(WRITE_READBACK_SEC)
    after_fc16 = read_holding(host, port, slave, REG_START, REG_COUNT)
    print("after FC16:", format_values(after_fc16, slave))
    if after_fc16 is not None and after_fc16[0] == target:
        print("Power register matches target via FC16.")
        return 0

    print("Register unchanged after FC16; retrying FC06 (write single register).")
    fc06_ok = write_holding_fc06(host, port, slave, POWER_REG, target)
    print(f"FC06 response: {'ok' if fc06_ok else 'no/invalid response'}")
    time.sleep(WRITE_READBACK_SEC)
    after_fc06 = read_holding(host, port, slave, REG_START, REG_COUNT)
    print("after FC06:", format_values(after_fc06, slave))
    if after_fc06 is not None and after_fc06[0] == target:
        print("Power register matches target via FC06.")
        return 0

    print(
        "FAILED: Power register did not change. Confirm HA is stopped, "
        "slave/DIP, and RS485 A/B."
    )
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan ERV Modbus slaves, or read/write Power on one slave. "
            "A normal scan never writes."
        )
    )
    parser.add_argument("--host", default=HOST, help=f"Modbus TCP host (default {HOST})")
    parser.add_argument(
        "--port", type=int, default=PORT, help=f"Modbus TCP port (default {PORT})"
    )
    parser.add_argument("--slave", type=int, metavar="N", help="Single slave id")
    parser.add_argument(
        "--read",
        action="store_true",
        help="Read holding registers 1-3 on --slave (Power/Mode/Air)",
    )
    parser.add_argument(
        "--power",
        choices=("on", "off"),
        help="Write Power register on --slave (FC16 first, then FC06). Not used during scan.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.power is not None or args.read:
        if args.slave is None:
            print("--slave N is required with --read or --power", file=sys.stderr)
            return 2
        if args.power is not None:
            return set_power(args.host, args.port, args.slave, args.power == "on")
        read_slave(args.host, args.port, args.slave)
        return 0
    if args.slave is not None:
        print("Use --slave N with --read or --power. A bare --slave is not a write.", file=sys.stderr)
        return 2
    scan(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
