#!/usr/bin/env python3
"""Scan ERV Modbus slaves behind HF5111SC.

Stop the Home Assistant ERV hub first. This gateway usually allows
only one TCP client at a time.
"""

from __future__ import annotations

import socket
import struct
import time

HOST = "172.17.24.160"
PORT = 8899
SLAVE_START = 1
SLAVE_END = 16
REG_START = 1
REG_COUNT = 3
TIMEOUT_SEC = 1.5
GAP_SEC = 0.2


def read_holding(host: str, port: int, slave: int, address: int, count: int) -> list[int] | None:
    req = struct.pack(
        ">HHHBBHH",
        1,  # transaction id
        0,  # protocol id
        6,  # remaining length
        slave,
        3,  # function: read holding registers
        address,
        count,
    )

    with socket.create_connection((host, port), timeout=TIMEOUT_SEC) as sock:
        sock.settimeout(TIMEOUT_SEC)
        sock.sendall(req)
        data = sock.recv(256)

    if len(data) < 9:
        return None

    _, _, _, unit, func, byte_count = struct.unpack(">HHHBBB", data[:9])
    if unit != slave or func != 3:
        return None
    if byte_count != count * 2 or len(data) < 9 + byte_count:
        return None

    values = []
    for i in range(count):
        values.append(struct.unpack(">H", data[9 + i * 2 : 11 + i * 2])[0])
    return values


def decode(power: int, mode: int, air: int) -> str:
    mode_txt = {0: "Heat-Exchange", 1: "Normal"}.get(mode, f"raw {mode}")
    air_txt = {1: "Low", 3: "High"}.get(air, f"raw {air}")
    return f"power={power}  mode={mode} ({mode_txt})  air={air} ({air_txt})"


def main() -> None:
    print(f"Scanning {HOST}:{PORT} slaves {SLAVE_START}-{SLAVE_END}")
    print("Read holding registers 1-3 = Power / Mode / Air")
    print("Close Home Assistant ERV connection before scanning.\n")

    found = []
    for slave in range(SLAVE_START, SLAVE_END + 1):
        try:
            values = read_holding(HOST, PORT, slave, REG_START, REG_COUNT)
        except OSError:
            values = None

        if values is None:
            print(f"slave {slave:>2}: no response")
        else:
            found.append(slave)
            print(f"slave {slave:>2}: OK   {decode(*values)}")

        time.sleep(GAP_SEC)

    print()
    if found:
        print("Found slaves:", ", ".join(str(n) for n in found))
        print("Put these numbers into modbus.yaml as slave: for U1-U4")
    else:
        print("No slave answered. Check DIP, ERV power, RS485 A/B, and that HA is disconnected.")


if __name__ == "__main__":
    main()
