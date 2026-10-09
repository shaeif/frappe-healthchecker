# Copyright (c) 2026, HC Tracker Maintainers and contributors
# For license information, please see license.txt

"""Who changed status, booked dates, due dates, engineers or reports, and who signed off - from the
document Version history of HC Contract."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, getdate, today

TRACKED = {
	"status": "Status",
	"scheduled_date": "Scheduled Date",
	"next_due_date": "Next Due Date",
	"assigned_engineer": "Assigned Engineer",
	"account_manager": "Account Manager",
	"technical_manager": "Technical Manager",
	"current_report": "Current Report",
	"current_signoff": "Current Sign-off",
	"frequency": "HC Frequency",
	"notification_flow": "Notification Flow",
	"reminders_paused_until": "Reminders Paused Until",
	"contract_end": "Contract End",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = getdate(filters.from_date or add_days(today(), -30))
	to_date = getdate(filters.to_date or today())
	columns = [
		{"label": _("Changed On"), "fieldname": "changed_on", "fieldtype": "Datetime", "width": 160},
		{"label": _("User"), "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 180},
		{"label": _("Contract"), "fieldname": "contract", "fieldtype": "Link", "options": "HC Contract", "width": 100},
		{"label": _("Client"), "fieldname": "client", "fieldtype": "Data", "width": 170},
		{"label": _("Change"), "fieldname": "change", "fieldtype": "Data", "width": 160},
		{"label": _("Old Value"), "fieldname": "old", "fieldtype": "Data", "width": 180},
		{"label": _("New Value"), "fieldname": "new", "fieldtype": "Data", "width": 180},
	]
	contracts = {
		c.name: c.client_name
		for c in frappe.get_list("HC Contract", fields=["name", "client_name"], limit_page_length=0)
	}
	vfilters = {
		"ref_doctype": "HC Contract",
		"creation": ["between", [str(from_date), str(add_to_date(to_date, days=1))]],
	}
	if filters.contract:
		vfilters["docname"] = filters.contract
	if filters.user:
		vfilters["owner"] = filters.user
	versions = frappe.get_all(
		"Version", filters=vfilters, fields=["docname", "owner", "creation", "data"], order_by="creation desc"
	)
	data = []
	for v in versions:
		if v.docname not in contracts:
			continue
		try:
			payload = json.loads(v.data or "{}")
		except ValueError:
			continue
		base = {"changed_on": v.creation, "user": v.owner, "contract": v.docname, "client": contracts[v.docname]}
		for field, old, new in payload.get("changed") or []:
			if field not in TRACKED or (filters.field and filters.field != TRACKED[field]):
				continue
			data.append({**base, "change": _(TRACKED[field]), "old": _(str(old)) if old else "", "new": _(str(new)) if new else ""})
		for table, row in payload.get("added") or []:
			if table == "cycles" and (not filters.field or filters.field == "Sign-off"):
				data.append({**base, "change": _("Sign-off"), "old": row.get("period_label"), "new": _("Signed off by {0}").format(row.get("signed_off_by") or v.owner)})
			if table == "reschedules" and (not filters.field or filters.field == "Scheduled Date"):
				data.append({**base, "change": _("Reschedule reason"), "old": str(row.get("old_date") or ""), "new": f"{row.get('new_date')} - {_(row.get('reason') or '')}"})
	return columns, data
