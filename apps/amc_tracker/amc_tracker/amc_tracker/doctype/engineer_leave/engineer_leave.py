# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, getdate


class EngineerLeave(Document):
	def validate(self):
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date cannot be before From Date."))
		visits = frappe.get_all(
			"PM Visit",
			filters={
				"engineer": self.engineer,
				"visit_date": ["between", [self.from_date, self.to_date]],
				"status": "Scheduled",
			},
			fields=["name", "client_name", "visit_date"],
		)
		if visits:
			frappe.msgprint(
				_("This engineer has PM visits during the leave: {0}. Reschedule them.").format(
					", ".join(f"{v.client_name} ({formatdate(v.visit_date)})" for v in visits)
				),
				title=_("Scheduled PM visits"),
				indicator="orange",
			)
