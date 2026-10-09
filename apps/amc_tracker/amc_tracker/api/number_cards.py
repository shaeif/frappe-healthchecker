"""Custom number card methods for the AMC Tracker dashboards.

Each uses frappe.get_list so counts respect the caller's row-level permissions (an engineer only counts
the AMCs and visits they are assigned to). The "my_*" cards are for the engineers' My Work page.
"""

import frappe
from frappe.utils import add_days, get_first_day, get_last_day, getdate, today

from amc_tracker.scheduling import next_working_days


def _count(doctype: str, filters) -> int:
	return len(frappe.get_list(doctype, filters=filters, pluck="name", limit_page_length=0))


def _card(value, route_doctype, route_options=None, route=None):
	return {
		"value": value,
		"fieldtype": "Int",
		"route": route or ["List", route_doctype],
		"route_options": route_options or {},
	}


@frappe.whitelist()
def pm_due_this_month(filters=None):
	start, end = get_first_day(today()), get_last_day(today())
	f = {"status": "Active", "next_due_date": ["between", [start, end]]}
	return _card(_count("AMC", f), "AMC", {"next_due_date": ["between", [str(start), str(end)]], "status": "Active"})


@frappe.whitelist()
def pm_overdue(filters=None):
	f = [["status", "=", "Active"], ["next_due_date", "is", "set"], ["next_due_date", "<", today()]]
	return _card(_count("AMC", f), "AMC", {"next_due_date": ["<", today()], "status": "Active"})


@frappe.whitelist()
def engineers_to_assign(filters=None):
	horizon = frappe.db.get_single_value("AMC Settings", "todo_horizon_days") or 45
	f = [["status", "=", "Active"], ["cycle_status", "=", "Not started"], ["next_due_date", "<=", add_days(today(), horizon)]]
	return _card(_count("AMC", f), "AMC", {"cycle_status": "Not started", "status": "Active"})


@frappe.whitelist()
def visits_to_schedule(filters=None):
	return _card(_count("PM Visit", {"status": "To be scheduled"}), "PM Visit", {"status": "To be scheduled"})


@frappe.whitelist()
def visits_this_week(filters=None):
	start = getdate(today())
	end = add_days(start, 6)
	f = {"visit_date": ["between", [start, end]], "status": ["!=", "Cancelled"]}
	return _card(_count("PM Visit", f), "PM Visit", route=["List", "PM Visit", "Calendar", "default"])


@frappe.whitelist()
def reports_pending(filters=None):
	f = [["visit_date", "<", today()], ["status", "in", ["Scheduled", "Completed"]]]
	return _card(_count("PM Visit", f), "PM Visit", {"status": ["in", ["Scheduled", "Completed"]], "visit_date": ["<", today()]})


@frappe.whitelist()
def awaiting_sign_off(filters=None):
	return _card(_count("AMC", {"cycle_status": "Reports submitted"}), "AMC", {"cycle_status": "Reports submitted"})


@frappe.whitelist()
def follow_ups_due_today(filters=None):
	f = [["follow_up_on", "is", "set"], ["follow_up_on", "<=", today()]]
	amcs = {r.amc for r in frappe.get_list("Client Contact Log", filters=f, fields=["amc"], limit_page_length=0)}
	open_amcs = frappe.get_list(
		"AMC", filters={"status": "Active", "cycle_status": ["!=", "Reports submitted"], "name": ["in", list(amcs) or [""]]}, pluck="name"
	)
	return _card(len(open_amcs), None, route=["query-report", "PM To-Do"])


@frappe.whitelist()
def notifications_failed_today(filters=None):
	start = getdate(today())
	f = {"status": "Failed", "sent_on": [">=", f"{start} 00:00:00"]}
	return _card(_count("AMC Notification Log", f), "AMC Notification Log", {"status": "Failed", "sent_on": [">=", str(start)]})


# ---- Engineer "My Work" cards (engineers only see their own visits through permissions) ----


def _mine(filters: dict) -> dict:
	return {"engineer": frappe.session.user, **filters}


@frappe.whitelist()
def my_visits_to_schedule(filters=None):
	f = _mine({"status": "To be scheduled"})
	return _card(_count("PM Visit", f), "PM Visit", f)


@frappe.whitelist()
def my_visits_next_7_days(filters=None):
	start = getdate(today())
	f = _mine({"visit_date": ["between", [start, add_days(start, 6)]], "status": "Scheduled"})
	return _card(_count("PM Visit", f), "PM Visit", {"engineer": frappe.session.user, "status": "Scheduled"})


@frappe.whitelist()
def my_reports_pending(filters=None):
	f = _mine({"visit_date": ["<", today()], "status": ["in", ["Scheduled", "Completed"]]})
	return _card(_count("PM Visit", f), "PM Visit", {"engineer": frappe.session.user, "status": ["in", ["Scheduled", "Completed"]]})


@frappe.whitelist()
def my_next_working_day_visits(filters=None):
	day = next_working_days(today(), 1)[0]
	f = _mine({"visit_date": day, "status": "Scheduled"})
	return _card(_count("PM Visit", f), "PM Visit", {"engineer": frappe.session.user, "visit_date": str(day)})
