#!/usr/bin/env python3
"""Turn ERV Power on/off. This is NOT a scanner.

Stop Home Assistant ERV hub first (gateway allows one TCP client).

  python erv_power.py --slave 2 --power off
  python erv_power.py --slave 2 --power on
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time

HOST = "172.17.24.160"
PORT = 8899
TIMEOUT_SEC = 2.0
WRITE_READBACK_SEC = 0.4


def transact(request: bytes) -> bytes:
    with socket.create_connection((HOST, PORT), timeout=TIMEOUT_SEC) as sock:
        sock.settimeout(TIMEOUT_SEC)
        sock.sendall(request)
        return sock.recv(256)


def read_power_mode_air(slave: int) -> list[int] | None:
    req = struct.pack(">HHHBBHH", 1, 0, 6, slave, 3, 1, 3)
    try:
        data = transact(req)
    except OSError:
        return None
    if len(data) < 15:
        return None
    unit, func, byte_count = data[6], data[7], data[8]
    if unit != slave or func != 3 or byte_count != 6:
        return None
    return list(struct.unpack(">HHH", data[9:15]))


def write_fc16(slave: int, address: int, value: int) -> bool:
    req = struct.pack(">HHHBBHHBH", 1, 0, 9, slave, 16, address, 1, 2, value & 0xFFFF)
    try:
        data = transact(req)
    except OSError:
        return False
    if len(data) < 12:
        return False
    unit, func = data[6], data[7]
    addr, count = struct.unpack(">HH", data[8:12])
    return unit == slave and func == 16 and addr == address and count == 1


def fmt(values: list[int] | None, slave: int) -> str:
    if values is None:
        return f"slave {slave}: no response"
    power, mode, air = values
    return f"slave {slave}: power={power}  mode={mode}  air={air}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write ERV Power register. Not a scan.")
    parser.add_argument("--slave", type=int, required=True, help="Modbus slave id, e.g. 2 for U2")
    parser.add_argument("--power", choices=("on", "off"), required=True)
    args = parser.parse_args(argv)

    target = 1 if args.power == "on" else 0
    print("ERV POWER WRITE — this is not a scan")
    print(f"{HOST}:{PORT}  slave {args.slave}  power {args.power} (value {target})")
    print("Stop Home Assistant ERV hub first.\n")

    before = read_power_mode_air(args.slave)
    print("before:", fmt(before, args.slave))
    if before is None:
        print("FAILED: slave did not answer. Stop HA and check IP/RS485.")
        return 1
    if before[0] == target:
        print(f"Already power={target}. No write needed.")
        return 0

    ok = write_fc16(args.slave, 1, target)
    print("FC16 write:", "ok" if ok else "no/invalid response")
    time.sleep(WRITE_READBACK_SEC)
    after = read_power_mode_air(args.slave)
    print("after: ", fmt(after, args.slave))
    if after is not None and after[0] == target:
        print("DONE: Power register matches target.")
        return 0
    print("FAILED: Power did not change. HA may still own the gateway.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
