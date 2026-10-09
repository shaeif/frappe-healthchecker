# Copyright (c) 2026, HC Tracker Maintainers and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from hc_tracker.setup.default_flows import DEFAULT_FLOW_NAME, create_default_flows


class IntegrationTestHCNotificationFlow(IntegrationTestCase):
	def test_default_flows_exist(self):
		create_default_flows()
		self.assertTrue(frappe.db.exists("HC Notification Flow", DEFAULT_FLOW_NAME))
		for frequency in ("Monthly", "Quarterly", "Half-yearly", "Yearly"):
			self.assertTrue(frappe.db.exists("HC Notification Flow", f"{DEFAULT_FLOW_NAME} - {frequency}"))
		self.assertEqual(frappe.db.count("HC Notification Flow", {"is_default": 1}), 1)
