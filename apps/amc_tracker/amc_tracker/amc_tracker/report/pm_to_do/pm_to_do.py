# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, today

from amc_tracker.notifications.pm_todo import SECTIONS, build_todo


def execute(filters=None):
	filters = frappe._dict(filters or {})
	on_date = getdate(filters.date or today())
	columns = [
		{"label": _("Action"), "fieldname": "section", "fieldtype": "Data", "width": 230},
		{"label": _("Client"), "fieldname": "client", "fieldtype": "Data", "width": 170},
		{"label": _("AMC"), "fieldname": "amc", "fieldtype": "Link", "options": "AMC", "width": 125},
		{"label": _("PM Due"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Cycle Status"), "fieldname": "cycle_status", "fieldtype": "Data", "width": 135},
		{"label": _("Engineer"), "fieldname": "engineer", "fieldtype": "Data", "width": 140},
		{"label": _("PM Visit"), "fieldname": "visit", "fieldtype": "Link", "options": "PM Visit", "width": 130},
		{"label": _("Visit Date"), "fieldname": "visit_date", "fieldtype": "Date", "width": 100},
		{"label": _("Client Contact"), "fieldname": "contact", "fieldtype": "Data", "width": 220},
		{"label": _("Last Contact"), "fieldname": "last_contact", "fieldtype": "Data", "width": 170},
		{"label": _("Detail"), "fieldname": "detail", "fieldtype": "Data", "width": 220},
	]
	todo = build_todo(on_date)
	data = []
	for key, en, _ar in SECTIONS:
		if filters.section and filters.section != key:
			continue
		for row in todo.get(key) or []:
			data.append({**row, "section": _(en), "cycle_status": _(row["cycle_status"] or "")})
	return columns, data
