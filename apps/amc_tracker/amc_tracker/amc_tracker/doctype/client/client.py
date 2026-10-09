# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from amc_tracker.utils import split_list


class Client(Document):
	def before_validate(self):
		self.client_code = (self.client_code or "").strip().upper()
		self.client_name = (self.client_name or "").strip()

	def validate(self):
		self.status = self.status or "Active"
		if self.contact_email:
			frappe.utils.validate_email_address(self.contact_email.strip(), throw=True)
		for address in split_list(self.cc_emails):
			frappe.utils.validate_email_address(address, throw=True)

	def on_update(self):
		# Keep the client name shown on AMCs, visits and contact logs in sync
		if self.has_value_changed("client_name") and not self.is_new():
			for doctype in ("AMC", "PM Visit", "Client Contact Log"):
				frappe.db.set_value(doctype, {"client": self.name}, "client_name", self.client_name, update_modified=False)

	def on_trash(self):
		if frappe.db.exists("AMC", {"client": self.name}):
			frappe.throw(_("Client {0} has AMCs. Delete or move them first.").format(self.client_name))
