# Copyright (c) 2026, AMC Tracker Maintainers and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, getdate, today

from amc_tracker.cycle import assign_engineers, sign_off
from amc_tracker.notifications.engine import process_amc
from amc_tracker.utils import get_period_label

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "AMC Notification Flow", "Client", "Expertise"]

ENG1, ENG2 = "amc.test.eng1@example.com", "amc.test.eng2@example.com"


def ensure_engineer(email, first_name, expertise=()):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": first_name, "send_welcome_email": 0, "user_type": "System User"}
		).insert(ignore_permissions=True)
	for name in ("Routing & Switching", "Security / Firewall"):
		if not frappe.db.exists("Expertise", name):
			frappe.get_doc({"doctype": "Expertise", "expertise_name": name}).insert(ignore_permissions=True)
	if not frappe.db.exists("Engineer", email):
		frappe.get_doc(
			{"doctype": "Engineer", "user": email, "expertise": [{"expertise": x} for x in expertise]}
		).insert(ignore_permissions=True)


def make_amc(code, frequency="Quarterly", due_in_days=30, **kwargs):
	for name in frappe.get_all("AMC", filters={"client": code}, pluck="name"):
		frappe.db.delete("PM Visit", {"amc": name})
		frappe.delete_doc("AMC", name, force=True)
	if not frappe.db.exists("Client", code):
		frappe.get_doc({"doctype": "Client", "client_code": code, "client_name": f"Test client {code}"}).insert(ignore_permissions=True)
	for name in ("Routing & Switching", "Security / Firewall"):
		if not frappe.db.exists("Expertise", name):
			frappe.get_doc({"doctype": "Expertise", "expertise_name": name}).insert(ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "AMC",
			"client": code,
			"frequency": frequency,
			"next_due_date": add_days(today(), due_in_days),
			"engineers": [
				{"engineer": ENG1, "expertise": "Routing & Switching"},
				{"engineer": ENG2, "expertise": "Security / Firewall"},
			],
			**kwargs,
		}
	)
	return doc.insert(ignore_permissions=True)


class IntegrationTestAMC(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_engineer(ENG1, "Test Eng One", ["Routing & Switching", "Security / Firewall"])
		ensure_engineer(ENG2, "Test Eng Two", ["Security / Firewall"])

	def test_interval_title_and_period_label(self):
		doc = make_amc("TST-PL", "Half-yearly")
		self.assertEqual(doc.interval_months, 6)
		self.assertEqual(doc.amc_title, "Test client TST-PL AMC")
		self.assertEqual(doc.cycle_status, "Not started")
		self.assertEqual(get_period_label("2026-10-15", "Monthly"), "2026-10")
		self.assertEqual(get_period_label("2026-10-15", "Quarterly"), "2026-Q4")
		self.assertEqual(get_period_label("2026-10-15", "Half-yearly"), "2026-H2")
		self.assertEqual(get_period_label("2026-10-15", "Yearly"), "2026")

	def test_assign_creates_one_visit_per_engineer(self):
		doc = make_amc("TST-AS")
		result = assign_engineers(
			doc.name,
			[
				{"engineer": ENG1, "expertise": ["Routing & Switching"]},
				{"engineer": ENG1, "expertise": ["Security / Firewall"]},  # same engineer, second area -> same visit
				{"engineer": ENG2, "expertise": ["Security / Firewall"], "visit_mode": "Remote"},
			],
		)
		self.assertEqual(len(result["created"]), 2)
		visits = frappe.get_all("PM Visit", filters={"amc": doc.name}, fields=["name", "engineer", "visit_mode", "status"])
		self.assertEqual({v.engineer for v in visits}, {ENG1, ENG2})
		self.assertTrue(all(v.status == "To be scheduled" for v in visits))
		eng1_visit = frappe.get_doc("PM Visit", next(v.name for v in visits if v.engineer == ENG1))
		self.assertEqual({r.expertise for r in eng1_visit.expertise_covered}, {"Routing & Switching", "Security / Firewall"})
		self.assertEqual(frappe.db.get_value("AMC", doc.name, "cycle_status"), "Engineers assigned")
		# assigning again skips engineers who already have a visit this cycle
		again = assign_engineers(doc.name, [{"engineer": ENG1, "expertise": []}])
		self.assertEqual(again["created"], [])

	def test_cycle_status_follows_visits_and_sign_off_rolls_due_date(self):
		doc = make_amc("TST-SO", "Quarterly", due_in_days=10)
		previous_due = getdate(doc.next_due_date)
		assign_engineers(doc.name, [{"engineer": ENG1, "expertise": ["Routing & Switching"]}, {"engineer": ENG2}])
		v1, v2 = (frappe.get_doc("PM Visit", {"amc": doc.name, "engineer": e}) for e in (ENG1, ENG2))

		v1.visit_date = add_days(today(), 2)
		v1.save()
		self.assertEqual(frappe.db.get_value("AMC", doc.name, "cycle_status"), "Engineers assigned")
		v2.visit_date = add_days(today(), 3)
		v2.save()
		self.assertEqual(frappe.db.get_value("AMC", doc.name, "cycle_status"), "Scheduled")

		# sign-off is refused while reports are missing
		self.assertRaises(frappe.ValidationError, sign_off, doc.name)

		v1.reload()
		v1.report = "/files/report1.pdf"
		v1.save()
		self.assertEqual(v1.status, "Report submitted")
		self.assertEqual(frappe.db.get_value("AMC", doc.name, "cycle_status"), "In progress")

		# v2 is covered by the combined report attached on the AMC
		v2.reload()
		v2.included_in_combined = 1
		v2.completed_on = add_days(today(), 3)
		v2.save()
		self.assertEqual(v2.status, "Completed")
		amc = frappe.get_doc("AMC", doc.name)
		amc.combined_report = "/files/combined.pdf"
		amc.save()
		self.assertEqual(frappe.db.get_value("PM Visit", v2.name, "status"), "Report submitted")
		self.assertEqual(frappe.db.get_value("AMC", doc.name, "cycle_status"), "Reports submitted")

		result = sign_off(doc.name)
		amc.reload()
		self.assertEqual(getdate(amc.next_due_date), getdate(add_months(previous_due, 3)))
		self.assertEqual(amc.cycle_status, "Not started")
		self.assertIsNone(amc.combined_report)
		self.assertEqual(len(amc.cycles), 1)
		self.assertEqual(amc.cycles[0].period_label, result["cycle"])
		self.assertEqual(amc.cycles[0].completed_on, getdate(add_days(today(), 3)))

	def test_engineer_profile_grants_role_and_holds_several_areas(self):
		self.assertIn("AMC Engineer", frappe.get_roles(ENG1))
		areas = frappe.get_all("Engineer Expertise", filters={"parent": ENG1}, pluck="expertise")
		self.assertEqual(set(areas), {"Routing & Switching", "Security / Firewall"})
		# an inactive engineer cannot be assigned
		doc = make_amc("TST-IN")
		frappe.db.set_value("Engineer", ENG2, "status", "Inactive")
		try:
			self.assertRaises(frappe.ValidationError, assign_engineers, doc.name, [{"engineer": ENG2}])
		finally:
			frappe.db.set_value("Engineer", ENG2, "status", "Active")

	def test_only_admin_controls_notification_rules(self):
		perms = {p.role: p for p in frappe.get_meta("AMC Notification Flow").permissions}
		self.assertEqual(set(perms), {"System Manager", "AMC Admin"})
		settings = {p.role: p.write for p in frappe.get_meta("AMC Settings").permissions}
		self.assertTrue(settings["AMC Admin"])
		self.assertFalse(settings.get("AMC Technical Manager"))

	def test_reschedule_is_recorded(self):
		doc = make_amc("TST-RS")
		assign_engineers(doc.name, [{"engineer": ENG1}])
		visit = frappe.get_doc("PM Visit", {"amc": doc.name})
		visit.visit_date = add_days(today(), 5)
		visit.save()
		visit.visit_date = add_days(today(), 8)
		visit.reschedule_reason = "Client request"
		visit.save()
		self.assertEqual(len(visit.reschedules), 1)
		self.assertEqual(visit.reschedules[0].reason, "Client request")
		self.assertIsNone(visit.reschedule_reason)

	def test_daily_run_is_idempotent(self):
		"""A second run on the same day sends nothing new (only channels that failed are retried)."""
		doc = make_amc("TST-ID", "Monthly", due_in_days=3)

		def sent():
			return frappe.db.count("AMC Notification Log", {"amc": doc.name, "status": "Sent"})

		process_amc(frappe.get_doc("AMC", doc.name))
		after_first = sent()
		process_amc(frappe.get_doc("AMC", doc.name))
		self.assertEqual(sent(), after_first)
