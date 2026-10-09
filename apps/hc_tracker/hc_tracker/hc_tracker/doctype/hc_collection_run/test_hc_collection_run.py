# Copyright (c) 2026, HC Tracker Maintainers and Contributors
# See license.txt

from datetime import date

from frappe.tests import IntegrationTestCase

from hc_tracker.collectors import parsers, simulator
from hc_tracker.collectors.base import DeviceResult, is_read_only_command
from hc_tracker.collectors.rules import Thresholds, evaluate

IGNORE_TEST_RECORD_DEPENDENCIES = ["HC Contract", "User"]


class IntegrationTestHCCollectionRun(IntegrationTestCase):
	def test_cisco_iosxe_parsers(self):
		out = simulator.IOSXE_SW["commands"]
		facts = parsers.cisco_ios_version(out["show version"])
		self.assertEqual(facts["software_version"], "17.09.04a")
		self.assertEqual(facts["model"], "C9300-48P")
		self.assertEqual(facts["serial_number"], "FOC2233X0AB")
		self.assertGreater(facts["uptime_days"], 400)
		self.assertEqual(parsers.cisco_cpu(out["show processes cpu | include CPU utilization"])["cpu_percent"], 85)
		self.assertEqual(parsers.cisco_ios_memory(out["show processes memory | include Processor Pool"])["memory_percent"], 46.0)

	def test_nxos_and_aireos_parsers(self):
		nx = simulator.NXOS["commands"]
		self.assertEqual(parsers.nxos_version(nx["show version"])["software_version"], "9.3(10)")
		res = parsers.nxos_resources(nx["show system resources"])
		self.assertAlmostEqual(res["cpu_percent"], 5.8, places=1)
		self.assertEqual(res["memory_percent"], 39.0)
		wlc = simulator.AIREOS["commands"]
		self.assertEqual(parsers.aireos_sysinfo(wlc["show sysinfo"])["software_version"], "8.10.185.0")
		self.assertEqual(parsers.cisco_ap_summary(wlc["show ap summary"])["ap_count"], 30)

	def test_uptime_formats(self):
		self.assertEqual(parsers.parse_uptime_days("120 day(s), 3 hour(s)"), 120.12)
		self.assertAlmostEqual(parsers.parse_uptime_days("520 days, 4:12:09"), 520.17, places=1)
		self.assertAlmostEqual(parsers.parse_uptime_days("1 year, 2 weeks, 3 days"), 382, places=0)

	def test_read_only_guard(self):
		self.assertTrue(is_read_only_command("show clock"))
		self.assertTrue(is_read_only_command("get system status"))
		self.assertFalse(is_read_only_command("reload"))
		self.assertFalse(is_read_only_command("configure terminal"))

	def test_rules(self):
		ok = DeviceResult("r1", "SW1", "10.0.0.1", "Cisco IOS-XE", "SSH (Netmiko)", status="Success",
			facts={"cpu_percent": 95, "memory_percent": 40, "uptime_days": 500, "software_version": "17.9",
				"licenses": [{"name": "DNA", "expires": "2026-01-01", "expired": False}]})
		bad = DeviceResult("r2", "SW2", "10.0.0.2", "Cisco IOS", "SSH (Netmiko)", status="Failed", error="timeout")
		findings = evaluate([ok, bad], Thresholds(), date(2026, 10, 10))
		titles = [(f.severity, f.device, f.title) for f in findings]
		self.assertIn(("Critical", "SW2", "Data collection failed"), titles)
		self.assertIn(("Critical", "SW1", "High CPU utilisation (95%)"), titles)
		self.assertIn(("Critical", "SW1", "License expired: DNA"), titles)
		self.assertIn(("Warning", "SW1", "Long uptime (500 days)"), titles)
		self.assertEqual(findings[0].severity, "Critical")
