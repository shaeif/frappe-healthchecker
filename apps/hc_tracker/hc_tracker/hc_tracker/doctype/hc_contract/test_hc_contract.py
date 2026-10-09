# Copyright (c) 2026, HC Tracker Maintainers and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from hc_tracker.notifications.engine import process_contract
from hc_tracker.utils import get_period_label

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "HC Notification Flow"]


def make_contract(client_id, frequency="Quarterly", due_in_days=30, **kwargs):
	if frappe.db.exists("HC Contract", client_id):
		frappe.delete_doc("HC Contract", client_id, force=True)
	doc = frappe.get_doc(
		{
			"doctype": "HC Contract",
			"client_id": client_id,
			"client_name": f"Test client {client_id}",
			"frequency": frequency,
			"next_due_date": add_days(today(), due_in_days),
			**kwargs,
		}
	)
	return doc.insert(ignore_permissions=True)


class IntegrationTestHCContract(IntegrationTestCase):
	def test_interval_and_period_label(self):
		doc = make_contract("TST-PL", "Half-yearly")
		self.assertEqual(doc.interval_months, 6)
		self.assertEqual(get_period_label("2026-10-15", "Monthly"), "2026-10")
		self.assertEqual(get_period_label("2026-10-15", "Quarterly"), "2026-Q4")
		self.assertEqual(get_period_label("2026-10-15", "Half-yearly"), "2026-H2")
		self.assertEqual(get_period_label("2026-10-15", "Yearly"), "2026")

	def test_report_attach_sets_report_sent(self):
		doc = make_contract("TST-RS")
		doc.current_report = "/files/test-report.pdf"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.status, "Report sent")

	def test_sign_off_requires_report(self):
		doc = make_contract("TST-SO1")
		doc.status = "Signed off"
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_sign_off_rolls_due_date_from_previous_due(self):
		doc = make_contract("TST-SO2", "Quarterly", due_in_days=-5)
		previous_due = getdate(doc.next_due_date)
		doc.current_report = "/files/test-report.pdf"
		doc.save(ignore_permissions=True)
		doc.status = "Signed off"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.status, "Not started")
		self.assertEqual(getdate(doc.next_due_date), frappe.utils.add_months(previous_due, 3))
		self.assertEqual(len(doc.cycles), 1)
		self.assertFalse(doc.current_report)

	def test_daily_run_is_idempotent(self):
		doc = make_contract("TST-IDEM", "Monthly", due_in_days=2)
		process_contract(doc)
		first = frappe.db.count("HC Notification Log", {"contract": doc.name})
		process_contract(doc)
		second = frappe.db.count("HC Notification Log", {"contract": doc.name})
		self.assertEqual(first, second)
