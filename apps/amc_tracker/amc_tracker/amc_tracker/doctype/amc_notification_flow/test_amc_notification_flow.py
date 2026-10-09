# Copyright (c) 2026, AMC Tracker Maintainers and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from amc_tracker.setup.default_flows import DEFAULT_FLOW_NAME, create_default_flows


class IntegrationTestAMCNotificationFlow(IntegrationTestCase):
	def test_default_rule_sets_exist(self):
		create_default_flows()
		self.assertTrue(frappe.db.exists("AMC Notification Flow", DEFAULT_FLOW_NAME))
		for frequency in ("Monthly", "Quarterly", "Half-yearly", "Yearly"):
			self.assertTrue(frappe.db.exists("AMC Notification Flow", f"{DEFAULT_FLOW_NAME} - {frequency}"))
		self.assertEqual(frappe.db.count("AMC Notification Flow", {"is_default": 1}), 1)

	def test_visit_engineer_needs_a_visit_trigger(self):
		flow = frappe.get_doc("AMC Notification Flow", DEFAULT_FLOW_NAME)
		flow.append(
			"steps",
			{"step_no": 99, "step_label": "Bad", "recipient_type": "Visit Engineer", "trigger_mode": "Days before due date", "trigger_days": 1},
		)
		self.assertRaises(frappe.ValidationError, flow.save)
