# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PublicHoliday(Document):
	def on_change(self):
		frappe.local.amc_holiday_map = None
