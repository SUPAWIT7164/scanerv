#!/usr/bin/env python3
"""Turn on ERV U2 (Home Assistant entity switch.erv_u2_power).

Writes holding register 1 = 1 on Modbus slave 2 (FC16 first).
Stop the Home Assistant ERV hub first — HF5111SC allows one TCP client.
"""

from __future__ import annotations

from scan_erv import main

if __name__ == "__main__":
    raise SystemExit(main(["--slave", "2", "--power", "on"]))
