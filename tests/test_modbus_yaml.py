#!/usr/bin/env python3
"""modbus.yaml must be a two-hub list so Home Assistant can include it."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODBUS_YAML = ROOT / "ha" / "modbus.yaml"


class ModbusYamlTests(unittest.TestCase):
    def test_file_parses_as_two_sibling_hubs(self) -> None:
        text = MODBUS_YAML.read_text(encoding="utf-8")
        data = yaml.safe_load(text)

        self.assertIsInstance(data, list)
        self.assertEqual([hub["name"] for hub in data], ["ERV", "intesis_panasonic"])

        starts = [line for line in text.splitlines() if line.startswith("- name:")]
        self.assertEqual(starts, ['- name: "ERV"', '- name: "intesis_panasonic"'])

    def test_erv_hub(self) -> None:
        erv = yaml.safe_load(MODBUS_YAML.read_text(encoding="utf-8"))[0]
        self.assertEqual(erv["type"], "tcp")
        self.assertEqual(erv["host"], "172.17.24.160")
        self.assertEqual(erv["port"], 8899)
        self.assertEqual(len(erv["switches"]), 4)
        self.assertEqual(len(erv["sensors"]), 16)
        for switch in erv["switches"]:
            self.assertEqual(switch["write_type"], "holdings")
            self.assertEqual(switch["verify"]["address"], 1)

    def test_intesis_hub(self) -> None:
        intesis = yaml.safe_load(MODBUS_YAML.read_text(encoding="utf-8"))[1]
        self.assertEqual(intesis["type"], "tcp")
        self.assertEqual(intesis["host"], "172.17.24.120")
        self.assertEqual(intesis["port"], 502)
        climates = intesis["climates"]
        self.assertEqual(len(climates), 35)
        self.assertEqual(climates[0]["name"], "FCU1")
        self.assertEqual(climates[0]["slave"], 2)
        self.assertEqual(climates[-1]["name"], "FCU35")
        self.assertEqual(climates[-1]["slave"], 36)

    def test_mixed_indent_is_the_original_parse_error(self) -> None:
        broken = (
            '  - name: "ERV"\n'
            "    type: tcp\n"
            "\n"
            '- name: "intesis_panasonic"\n'
            "  type: tcp\n"
        )
        with self.assertRaises(yaml.YAMLError):
            yaml.safe_load(broken)


if __name__ == "__main__":
    unittest.main()
