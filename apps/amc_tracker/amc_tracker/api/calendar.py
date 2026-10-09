"""PM Calendar (PM Visit > Calendar view).

One event per dated PM visit, coloured by status. AMCs due in the period that still have visits without a date
appear as "PM due" markers. Holidays and, when filtered by engineer, their leave are shaded in the background.
Dragging a visit changes its date (recorded in its Reschedule History as "Changed in calendar").
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, getdate, today

from amc_tracker.utils import VISIT_CANCELLED

STATUS_COLORS = {
	"Scheduled": "#2490ef",
	"Completed": "#f39c12",
	"Report submitted": "#27ae60",
}


def _engineer_filter(filters) -> str | None:
	if isinstance(filters, str):
		filters = json.loads(filters or "[]")
	for f in filters or []:
		if isinstance(f, list | tuple) and len(f) >= 4 and f[1] == "engineer" and f[2] == "=":
			return f[3]
		if isinstance(f, dict) and f.get("engineer"):
			return f["engineer"]
	return None


def _event(name, title, day, color, end=None, **kw):
	return {
		"name": name,
		"title": title,
		"start": str(day),
		"end": str(end or day),
		"allDay": 1,
		"convert_to_user_tz": 0,
		"color": color,
		**kw,
	}


@frappe.whitelist()
def get_events(start, end, filters=None, **kwargs):
	start, end = getdate(start), getdate(end)
	if isinstance(filters, str):
		filters = json.loads(filters or "[]")
	visit_filters = [
		*(filters or []),
		["PM Visit", "status", "!=", VISIT_CANCELLED],
		["PM Visit", "visit_date", "between", [start, end]],
	]
	events = []
	for v in frappe.get_list(
		"PM Visit",
		filters=visit_filters,
		fields=["name", "client_name", "engineer_name", "engineer", "status", "visit_date", "visit_mode"],
		limit_page_length=0,
	):
		mode = _("Remote") if v.visit_mode == "Remote" else _("On-site")
		events.append(
			_event(
				v.name,
				f"{v.client_name} · {v.engineer_name or v.engineer} ({mode})",
				getdate(v.visit_date),
				STATUS_COLORS.get(v.status, "#7f8c8d"),
			)
		)

	# AMCs due in the window with visits still to be scheduled (or no engineers yet)
	now = getdate(today())
	for a in frappe.get_list(
		"AMC",
		filters={"status": "Active", "next_due_date": ["between", [start, end]], "cycle_status": ["in", ["Not started", "Engineers assigned"]]},
		fields=["name", "client_name", "next_due_date", "cycle_status"],
		limit_page_length=0,
	):
		days = date_diff(a.next_due_date, now)
		color = "#e74c3c" if days < 0 else ("#e67e22" if days <= 14 else "#95a5a6")
		label = _("PM due: {0} (engineers to assign)") if a.cycle_status == "Not started" else _("PM due: {0} (dates to set)")
		events.append(_event(f"due::{a.name}", label.format(a.client_name), getdate(a.next_due_date), color, editable=0))

	for h in frappe.get_all(
		"Public Holiday", filters={"holiday_date": ["between", [start, end]]}, fields=["holiday_date", "description"]
	):
		events.append(_event(f"holiday::{h.holiday_date}", h.description, h.holiday_date, "#f5b7b1", display="background"))

	engineer = _engineer_filter(filters)
	if engineer:
		for lv in frappe.get_all(
			"Engineer Leave",
			filters={"engineer": engineer, "from_date": ["<=", end], "to_date": [">=", start]},
			fields=["name", "from_date", "to_date", "leave_type"],
		):
			events.append(
				_event(f"leave::{lv.name}", _(lv.leave_type), lv.from_date, "#d5d8dc", end=add_days(lv.to_date, 1), display="background")
			)
	return events


@frappe.whitelist()
def update_event(args, field_map=None):
	"""Calendar drag & drop: move a PM visit to the dropped day."""
	args = frappe._dict(json.loads(args) if isinstance(args, str) else args)
	name = str(args.name or "")
	if name.startswith("due::"):
		frappe.throw(_("A PM due date cannot be moved here. Assign engineers on the AMC; each engineer sets the visit date."))
	if "::" in name:
		frappe.throw(_("Holidays and leave cannot be moved here."))
	doc = frappe.get_doc("PM Visit", name)
	doc.check_permission("write")
	new_date = getdate(args.start)
	if doc.visit_date and getdate(doc.visit_date) == new_date:
		return doc.status
	if doc.visit_date:
		doc.reschedule_reason = "Changed in calendar"
	doc.visit_date = new_date
	doc.save()
	return doc.status
