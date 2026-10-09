# Copyright (c) 2026, HC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, getdate


class HCEngineerLeave(Document):
	def validate(self):
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date cannot be before From Date."))
		booked = frappe.get_all(
			"HC Contract",
			filters={
				"assigned_engineer": self.engineer,
				"scheduled_date": ["between", [self.from_date, self.to_date]],
				"status": ["in", ["Scheduled", "In progress"]],
			},
			fields=["name", "client_name", "scheduled_date"],
		)
		if booked:
			frappe.msgprint(
				_("This engineer already has health checks booked during the leave: {0}. Reschedule them.").format(
					", ".join(f"{b.client_name} ({formatdate(b.scheduled_date)})" for b in booked)
				),
				title=_("Booked health checks"),
				indicator="orange",
			)
