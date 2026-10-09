# Copyright (c) 2026, HC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from hc_tracker.notifications.helpdesk_todo import SECTIONS, build_todo


def execute(filters=None):
	filters = frappe._dict(filters or {})
	todo = build_todo(filters.date)
	columns = [
		{"label": _("Action"), "fieldname": "section", "fieldtype": "Data", "width": 230},
		{"label": _("Contract"), "fieldname": "contract", "fieldtype": "Link", "options": "HC Contract", "width": 100},
		{"label": _("Client"), "fieldname": "client", "fieldtype": "Data", "width": 180},
		{"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": _("Engineer"), "fieldname": "engineer", "fieldtype": "Data", "width": 140},
		{"label": _("Client Contact"), "fieldname": "contact", "fieldtype": "Data", "width": 220},
		{"label": _("Last Contact"), "fieldname": "last_contact", "fieldtype": "Data", "width": 200},
		{"label": _("Detail"), "fieldname": "detail", "fieldtype": "Data", "width": 260},
	]
	allowed = set(frappe.get_list("HC Contract", pluck="name", limit_page_length=0))
	data = []
	for key, label, _ar in SECTIONS:
		if filters.section and filters.section != label:
			continue
		for row in todo.get(key) or []:
			if row["contract"] in allowed:
				data.append({"section": _(label), **row})
	return columns, data
