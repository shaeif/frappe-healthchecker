# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from amc_tracker.utils import split_list


class AMCSettings(Document):
	def validate(self):
		for fieldname in ("digest_recipients", "management_summary_recipients"):
			for address in split_list(self.get(fieldname)):
				frappe.utils.validate_email_address(address, throw=True)
		for fieldname in ("renewal_alert_days", "todo_horizon_days", "client_reply_wait_days"):
			if cint(self.get(fieldname)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(fieldname))))
		if cint(self.enable_teams) and not (self.default_teams_webhook_url or "").strip():
			frappe.msgprint(
				_("Teams is enabled but no default webhook URL is set. Rules without their own URL will fail."),
				indicator="orange",
				alert=True,
			)

	def on_update(self):
		frappe.local.amc_holiday_map = None
