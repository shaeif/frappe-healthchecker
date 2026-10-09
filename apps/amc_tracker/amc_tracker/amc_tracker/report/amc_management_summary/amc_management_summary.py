# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from amc_tracker.notifications.summary import build_summary, totals


def execute(filters=None):
	filters = frappe._dict(filters or {})
	to_date = getdate(filters.to_date or today())
	from_date = getdate(filters.from_date or add_days(to_date, -30))
	group_by = filters.group_by or "Client"
	rows = build_summary(from_date, to_date, group_by)
	unit = _("PM cycles") if group_by == "Client" else _("PM visits")
	columns = [
		{"label": _("Client / AMC") if group_by == "Client" else _("Engineer"), "fieldname": "key", "fieldtype": "Data", "width": 280},
		{"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int", "width": 100},
		{"label": _("On time"), "fieldname": "on_time", "fieldtype": "Int", "width": 90},
		{"label": _("Late"), "fieldname": "late", "fieldtype": "Int", "width": 80},
		{"label": _("On-time %"), "fieldname": "on_time_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Avg days vs due date"), "fieldname": "avg_days_to_signoff", "fieldtype": "Float", "width": 160},
		{"label": _("Pending"), "fieldname": "pending", "fieldtype": "Int", "width": 90},
		{"label": _("Overdue"), "fieldname": "overdue", "fieldtype": "Int", "width": 90},
	]
	t = totals(rows)
	chart = {
		"data": {
			"labels": [_("Completed"), _("On time"), _("Late"), _("Pending"), _("Overdue")],
			"datasets": [{"name": unit, "values": [t["completed"], t["on_time"], t["late"], t["pending"], t["overdue"]]}],
		},
		"type": "bar",
		"colors": ["#0b4f8a"],
	}
	summary = [
		{"label": _("Completed"), "value": t["completed"], "indicator": "Blue"},
		{"label": _("On-time %"), "value": f"{t['on_time_pct']}%" if t["on_time_pct"] is not None else "-", "indicator": "Green"},
		{"label": _("Pending"), "value": t["pending"], "indicator": "Orange"},
		{"label": _("Overdue"), "value": t["overdue"], "indicator": "Red"},
	]
	return columns, rows, None, chart, summary
