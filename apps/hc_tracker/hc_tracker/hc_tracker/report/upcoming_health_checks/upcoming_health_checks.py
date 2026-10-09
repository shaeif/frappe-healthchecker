# Copyright (c) 2026, HC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Client ID"), "fieldname": "name", "fieldtype": "Link", "options": "HC Contract", "width": 110},
		{"label": _("Client"), "fieldname": "client_name", "fieldtype": "Data", "width": 200},
		{"label": _("Frequency"), "fieldname": "frequency", "fieldtype": "Data", "width": 100},
		{"label": _("Next Due Date"), "fieldname": "next_due_date", "fieldtype": "Date", "width": 115},
		{"label": _("Days Left"), "fieldname": "days_left", "fieldtype": "Int", "width": 90},
		{"label": _("Scheduled Date"), "fieldname": "scheduled_date", "fieldtype": "Date", "width": 115},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Engineer"), "fieldname": "assigned_engineer", "fieldtype": "Link", "options": "User", "width": 170},
		{"label": _("Engineer Name"), "fieldname": "engineer_name", "fieldtype": "Data", "width": 140},
		{"label": _("Account Manager"), "fieldname": "account_manager", "fieldtype": "Link", "options": "User", "width": 170},
		{"label": _("Last HC Date"), "fieldname": "last_hc_date", "fieldtype": "Date", "width": 110},
	]


def get_data(filters):
	start = getdate(today())
	end = add_days(start, cint(filters.days) or 90)
	conditions = {"status": ["!=", "Signed off"]}
	if cint(filters.include_overdue):
		conditions["next_due_date"] = ["<=", end]
	else:
		conditions["next_due_date"] = ["between", [start, end]]
	if filters.engineer:
		conditions["assigned_engineer"] = filters.engineer
	if filters.status:
		conditions["status"] = filters.status

	rows = frappe.get_list(
		"HC Contract",
		filters=conditions,
		fields=[
			"name",
			"client_name",
			"frequency",
			"next_due_date",
			"scheduled_date",
			"status",
			"assigned_engineer",
			"engineer_name",
			"account_manager",
			"last_hc_date",
		],
		order_by="next_due_date asc",
		limit_page_length=0,
	)
	for row in rows:
		row.days_left = date_diff(row.next_due_date, start)
	return rows
