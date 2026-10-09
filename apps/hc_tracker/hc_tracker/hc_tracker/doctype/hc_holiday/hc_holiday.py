# Copyright (c) 2026, HC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HCHoliday(Document):
	def on_change(self):
		frappe.local.hc_holiday_map = None
