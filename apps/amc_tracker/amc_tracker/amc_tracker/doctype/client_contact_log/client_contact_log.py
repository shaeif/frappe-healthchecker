# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class ClientContactLog(Document):
	def validate(self):
		self.logged_by = self.logged_by or frappe.session.user
		if self.pause_reminders_until and getdate(self.pause_reminders_until) < getdate(self.contact_on):
			frappe.throw(_("Pause Reminders Until must be after the contact date."))
		if self.pm_visit and frappe.db.get_value("PM Visit", self.pm_visit, "amc") != self.amc:
			frappe.throw(_("PM Visit {0} belongs to another AMC.").format(self.pm_visit))

	def after_insert(self):
		values = {"last_contact_on": self.contact_on, "last_contact_outcome": self.outcome}
		if self.pause_reminders_until:
			values["reminders_paused_until"] = self.pause_reminders_until
		if self.outcome == "Scheduling email sent":
			values["scheduling_email_sent_on"] = self.contact_on
		frappe.db.set_value("AMC", self.amc, values)
		frappe.get_doc("AMC", self.amc).add_comment(
			"Info",
			_("Contact logged: {0} via {1}{2}").format(
				_(self.outcome), _(self.method), f" - {self.notes}" if self.notes else ""
			),
		)


@frappe.whitelist()
def log_contact(amc: str, **values) -> str:
	"""Create a contact log from the AMC / PM Visit form dialog."""
	frappe.get_doc("AMC", amc).check_permission("read")
	doc = frappe.new_doc("Client Contact Log")
	doc.amc = amc
	for key in ("pm_visit", "contact_on", "method", "direction", "outcome", "proposed_date", "follow_up_on", "pause_reminders_until", "notes"):
		if values.get(key):
			doc.set(key, values[key])
	doc.insert()
	return doc.name
