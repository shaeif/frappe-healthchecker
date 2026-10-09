# Copyright (c) 2026, HC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from hc_tracker.notifications.summary import build_summary, totals


def execute(filters=None):
	filters = frappe._dict(filters or {})
	to_date = getdate(filters.to_date or today())
	from_date = getdate(filters.from_date or add_days(to_date, -30))
	group_by = filters.group_by or "Client"
	rows = build_summary(from_date, to_date, group_by)
	columns = [
		{"label": _(group_by), "fieldname": "key", "fieldtype": "Data", "width": 240},
		{"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int", "width": 100},
		{"label": _("On time"), "fieldname": "on_time", "fieldtype": "Int", "width": 90},
		{"label": _("Late"), "fieldname": "late", "fieldtype": "Int", "width": 80},
		{"label": _("On-time %"), "fieldname": "on_time_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Avg days due to sign-off"), "fieldname": "avg_days_to_signoff", "fieldtype": "Float", "width": 170},
		{"label": _("Pending"), "fieldname": "pending", "fieldtype": "Int", "width": 90},
		{"label": _("Overdue"), "fieldname": "overdue", "fieldtype": "Int", "width": 90},
	]
	t = totals(rows)
	chart = {
		"data": {
			"labels": [_("Completed"), _("On time"), _("Late"), _("Pending"), _("Overdue")],
			"datasets": [{"name": _("Health checks"), "values": [t["completed"], t["on_time"], t["late"], t["pending"], t["overdue"]]}],
		},
		"type": "bar",
		"colors": ["#2490ef"],
	}
	return columns, rows, None, chart
