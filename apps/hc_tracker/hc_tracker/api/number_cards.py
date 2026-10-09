"""Custom number card methods for the HC Tracker workspace.

Each uses frappe.get_list so the counts respect the caller's row-level permissions
(an engineer sees counts for their own contracts only).
"""

import frappe
from frappe.utils import add_days, get_first_day, get_last_day, getdate, today


def _count(doctype: str, filters) -> int:
	return len(frappe.get_list(doctype, filters=filters, pluck="name", limit_page_length=0))


@frappe.whitelist()
def due_this_month(filters=None):
	start, end = get_first_day(today()), get_last_day(today())
	f = {"next_due_date": ["between", [start, end]], "status": ["!=", "Signed off"]}
	return {
		"value": _count("HC Contract", f),
		"fieldtype": "Int",
		"route": ["List", "HC Contract"],
		"route_options": {"next_due_date": ["between", [str(start), str(end)]]},
	}


@frappe.whitelist()
def overdue(filters=None):
	f = {"next_due_date": ["<", today()], "status": ["!=", "Signed off"]}
	return {
		"value": _count("HC Contract", f),
		"fieldtype": "Int",
		"route": ["List", "HC Contract"],
		"route_options": {"next_due_date": ["<", today()]},
	}


@frappe.whitelist()
def awaiting_sign_off(filters=None):
	return {
		"value": _count("HC Contract", {"status": "Report sent"}),
		"fieldtype": "Int",
		"route": ["List", "HC Contract"],
		"route_options": {"status": "Report sent"},
	}


@frappe.whitelist()
def notifications_failed_today(filters=None):
	start = getdate(today())
	f = {"status": "Failed", "sent_on": [">=", f"{start} 00:00:00"]}
	return {
		"value": _count("HC Notification Log", f),
		"fieldtype": "Int",
		"route": ["List", "HC Notification Log"],
		"route_options": {"status": "Failed", "sent_on": [">=", str(start)]},
	}


@frappe.whitelist()
def follow_ups_due_today(filters=None):
	f = {"follow_up_on": ["<=", today()]}
	names = {r.contract for r in frappe.get_list("HC Contact Log", filters=f, fields=["contract"], limit_page_length=0)}
	open_names = set(frappe.get_list("HC Contract", filters={"status": "Not started", "name": ["in", list(names) or [""]]}, pluck="name"))
	return {
		"value": len(open_names),
		"fieldtype": "Int",
		"route": ["query-report", "Helpdesk To-Do"],
		"route_options": {},
	}
