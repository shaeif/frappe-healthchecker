# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

"""Who changed what on AMCs and PM visits (engineers, dates, reports, sign-offs), from the document
Version history."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, getdate, today

TRACKED = {
	"AMC": {
		"status": "Contract Status",
		"next_due_date": "Next PM Due Date",
		"frequency": "PM Frequency",
		"account_manager": "Account Manager",
		"technical_manager": "Technical Manager",
		"combined_report": "Combined PM Report",
		"client_signoff": "Client Sign-off",
		"notification_flow": "Notification Rules",
		"reminders_paused_until": "Reminders Paused Until",
		"contract_end": "Contract End",
	},
	"PM Visit": {
		"engineer": "Engineer",
		"visit_date": "Visit Date",
		"visit_mode": "Visit Mode",
		"status": "Visit Status",
		"report": "Visit Report",
		"included_in_combined": "Included in the combined AMC report",
	},
}
CHANGES = ["Engineer assigned", "Engineers", "Visit Date", "Visit Status", "Visit Report", "Sign-off", "Next PM Due Date", "Contract Status"]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = getdate(filters.from_date or add_days(today(), -30))
	to_date = getdate(filters.to_date or today())
	columns = [
		{"label": _("Changed On"), "fieldname": "changed_on", "fieldtype": "Datetime", "width": 160},
		{"label": _("User"), "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 170},
		{"label": _("Client"), "fieldname": "client", "fieldtype": "Data", "width": 160},
		{"label": _("AMC"), "fieldname": "amc", "fieldtype": "Link", "options": "AMC", "width": 125},
		{"label": _("PM Visit"), "fieldname": "visit", "fieldtype": "Link", "options": "PM Visit", "width": 130},
		{"label": _("Change"), "fieldname": "change", "fieldtype": "Data", "width": 160},
		{"label": _("Old Value"), "fieldname": "old", "fieldtype": "Data", "width": 170},
		{"label": _("New Value"), "fieldname": "new", "fieldtype": "Data", "width": 200},
	]
	amcs = {a.name: a.client_name for a in frappe.get_list("AMC", fields=["name", "client_name"], limit_page_length=0)}
	visits = {
		v.name: v
		for v in frappe.get_list("PM Visit", fields=["name", "amc", "client_name"], filters={"amc": ["in", list(amcs) or [""]]}, limit_page_length=0)
	}
	period = ["between", [str(from_date), str(add_to_date(to_date, days=1))]]
	data = []
	for doctype in ("AMC", "PM Visit"):
		vfilters = {"ref_doctype": doctype, "creation": period}
		if filters.user:
			vfilters["owner"] = filters.user
		if doctype == "AMC" and filters.amc:
			vfilters["docname"] = filters.amc
		for v in frappe.get_all("Version", filters=vfilters, fields=["docname", "owner", "creation", "data"], order_by="creation desc"):
			if doctype == "AMC":
				if v.docname not in amcs:
					continue
				base = {"changed_on": v.creation, "user": v.owner, "amc": v.docname, "client": amcs[v.docname], "visit": None}
			else:
				visit = visits.get(v.docname)
				if not visit or (filters.amc and visit.amc != filters.amc):
					continue
				base = {"changed_on": v.creation, "user": v.owner, "amc": visit.amc, "client": visit.client_name, "visit": v.docname}
			try:
				payload = json.loads(v.data or "{}")
			except ValueError:
				continue
			data.extend(_rows(doctype, base, payload, v.owner, filters.change))
	# Visits created = engineers assigned to a PM cycle (a new document has no Version yet)
	if not filters.change or filters.change == "Engineer assigned":
		vf = {"amc": ["in", list(amcs) or [""]], "creation": period}
		if filters.amc:
			vf["amc"] = filters.amc
		if filters.user:
			vf["owner"] = filters.user
		for v in frappe.get_all("PM Visit", filters=vf, fields=["name", "amc", "client_name", "engineer_name", "engineer", "cycle_label", "owner", "creation"]):
			data.append(
				{
					"changed_on": v.creation, "user": v.owner, "amc": v.amc, "client": v.client_name, "visit": v.name,
					"change": _("Engineer assigned"), "old": v.cycle_label, "new": v.engineer_name or v.engineer,
				}
			)
	data.sort(key=lambda r: r["changed_on"], reverse=True)
	return columns, data


def _rows(doctype, base, payload, owner, only):
	out = []

	def add(change, old, new):
		if not only or only == change:
			out.append({**base, "change": _(change), "old": old, "new": new})

	for field, old, new in payload.get("changed") or []:
		label = TRACKED[doctype].get(field)
		if label:
			add(label, _(str(old)) if old not in (None, "") else "", _(str(new)) if new not in (None, "") else "")
	for table, row in payload.get("added") or []:
		if doctype == "AMC" and table == "cycles":
			add("Sign-off", row.get("period_label"), _("Signed off by {0}").format(row.get("signed_off_by") or owner))
		elif doctype == "AMC" and table == "engineers":
			add("Engineers", "", f"+ {row.get('engineer')} ({row.get('expertise') or '-'})")
		elif doctype == "PM Visit" and table == "reschedules":
			add("Visit Date", str(row.get("old_date") or ""), f"{row.get('new_date')} - {_(row.get('reason') or '')}")
	for table, row in payload.get("removed") or []:
		if doctype == "AMC" and table == "engineers":
			add("Engineers", f"- {row.get('engineer')} ({row.get('expertise') or '-'})", "")
	return out
