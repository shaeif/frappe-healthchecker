# Copyright (c) 2026, HC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder import Interval
from frappe.query_builder.functions import Now


class HCNotificationLog(Document):
	@staticmethod
	def clear_old_logs(days=365):
		table = frappe.qb.DocType("HC Notification Log")
		frappe.db.delete(table, filters=(table.creation < (Now() - Interval(days=days))))
