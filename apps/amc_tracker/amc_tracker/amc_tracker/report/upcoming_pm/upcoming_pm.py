# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, formatdate, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("AMC"), "fieldname": "name", "fieldtype": "Link", "options": "AMC", "width": 125},
		{"label": _("Client"), "fieldname": "client_name", "fieldtype": "Data", "width": 180},
		{"label": _("AMC Name"), "fieldname": "amc_title", "fieldtype": "Data", "width": 170},
		{"label": _("PM Frequency"), "fieldname": "frequency", "fieldtype": "Data", "width": 105},
		{"label": _("PM Due"), "fieldname": "next_due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Days Left"), "fieldname": "days_left", "fieldtype": "Int", "width": 85},
		{"label": _("Cycle Status"), "fieldname": "cycle_status", "fieldtype": "Data", "width": 140},
		{"label": _("Engineers (visit date)"), "fieldname": "engineers", "fieldtype": "Data", "width": 280},
		{"label": _("Account Manager"), "fieldname": "account_manager", "fieldtype": "Link", "options": "User", "width": 160},
		{"label": _("Last PM Date"), "fieldname": "last_pm_date", "fieldtype": "Date", "width": 105},
	]


def get_data(filters):
	start = getdate(today())
	end = add_days(start, cint(filters.days) or 90)
	# list filters: "<=" alone would also match AMCs without a due date (NULL sorts as the earliest date)
	conditions = [["status", "=", "Active"], ["next_due_date", "is", "set"]]
	if cint(filters.include_overdue):
		conditions.append(["next_due_date", "<=", end])
	else:
		conditions.append(["next_due_date", "between", [start, end]])
	for field in ("client", "cycle_status", "frequency"):
		if filters.get(field):
			conditions.append([field, "=", filters.get(field)])
	if filters.engineer:
		amcs = set(frappe.get_all("AMC Engineer", filters={"engineer": filters.engineer, "parenttype": "AMC"}, pluck="parent"))
		conditions.append(["name", "in", list(amcs) or [""]])

	rows = frappe.get_list(
		"AMC",
		filters=conditions,
		fields=["name", "client_name", "amc_title", "frequency", "next_due_date", "cycle_status", "cycle_label", "account_manager", "last_pm_date"],
		order_by="next_due_date asc",
		limit_page_length=0,
	)
	visits = {}
	for v in frappe.get_all(
		"PM Visit",
		filters={"amc": ["in", [r.name for r in rows] or [""]], "status": ["!=", "Cancelled"]},
		fields=["amc", "cycle_label", "engineer_name", "engineer", "visit_date"],
		order_by="visit_date asc",
	):
		visits.setdefault((v.amc, v.cycle_label), []).append(
			f"{v.engineer_name or v.engineer} ({formatdate(v.visit_date) if v.visit_date else _('no date')})"
		)
	for r in rows:
		r.days_left = date_diff(r.next_due_date, start)
		r.cycle_status = _(r.cycle_status or "")
		r.engineers = ", ".join(visits.get((r.name, r.cycle_label), [])) or _("Not assigned")
		r.frequency = _(r.frequency or "")
	return rows
