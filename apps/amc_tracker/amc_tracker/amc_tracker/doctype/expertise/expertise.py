# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class Expertise(Document):
	def before_validate(self):
		self.expertise_name = (self.expertise_name or "").strip()
		if self.is_new() and self.enabled is None:
			self.enabled = 1
