# Copyright (c) 2026, HC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from hc_tracker.utils import split_list


class HCSettings(Document):
	def validate(self):
		for address in split_list(self.digest_recipients):
			frappe.utils.validate_email_address(address, throw=True)
		if cint(self.renewal_alert_days) < 0:
			frappe.throw(_("Renewal Alert Days cannot be negative."))
		if cint(self.enable_teams) and not (self.default_teams_webhook_url or "").strip():
			frappe.msgprint(
				_("Teams is enabled but no default webhook URL is set. Steps without their own URL will fail."),
				indicator="orange",
				alert=True,
			)
