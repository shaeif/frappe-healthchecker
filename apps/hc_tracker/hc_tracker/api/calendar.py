"""Helpdesk booking calendar (HC Contract > Calendar view).

One event per open contract: its booked date (Scheduled / In progress / Report sent) or, when not booked yet,
its due date. Dragging a booked event reschedules it ("Changed in calendar"); dragging an unbooked due-date
event onto a day books it (status Scheduled). Holidays and, when filtered by engineer, leave are shown as
background shading.
"""

import json

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

STATUS_COLORS = {"Scheduled": "#2490ef", "In progress": "#f39c12", "Report sent": "#8e44ad"}


def _engineer_filter(filters) -> str | None:
	if isinstance(filters, str):
		filters = json.loads(filters or "[]")
	for f in filters or []:
		if isinstance(f, list | tuple) and len(f) >= 4 and f[1] == "assigned_engineer" and f[2] == "=":
			return f[3]
		if isinstance(f, dict) and f.get("assigned_engineer"):
			return f["assigned_engineer"]
	return None


@frappe.whitelist()
def get_events(start, end, filters=None, **kwargs):
	start, end = getdate(start), getdate(end)
	if isinstance(filters, str):
		filters = json.loads(filters or "[]")
	base_filters = list(filters or []) + [["HC Contract", "status", "!=", "Signed off"]]
	rows = frappe.get_list(
		"HC Contract",
		filters=base_filters,
		fields=["name", "client_name", "status", "next_due_date", "scheduled_date", "engineer_name", "assigned_engineer"],
		limit_page_length=0,
	)
	now = getdate(today())
	events = []
	for r in rows:
		engineer = r.engineer_name or r.assigned_engineer or _("no engineer")
		if r.scheduled_date and r.status in STATUS_COLORS:
			day = getdate(r.scheduled_date)
			if start <= day <= end:
				events.append(
					{
						"name": r.name,
						"title": f"{r.client_name} · {engineer} ({_(r.status)})",
						"start": str(day),
						"end": str(day),
						"allDay": 1,
						"convert_to_user_tz": 0,
						"color": STATUS_COLORS[r.status],
					}
				)
		elif r.next_due_date:
			day = getdate(r.next_due_date)
			if start <= day <= end:
				days = date_diff(day, now)
				color = "#e74c3c" if days < 0 else ("#e67e22" if days <= 14 else "#95a5a6")
				events.append(
					{
						"name": r.name,
						"title": _("Due: {0} (not booked)").format(r.client_name),
						"start": str(day),
						"end": str(day),
						"allDay": 1,
						"convert_to_user_tz": 0,
						"color": color,
					}
				)

	for h in frappe.get_all(
		"HC Holiday", filters={"holiday_date": ["between", [start, end]]}, fields=["holiday_date", "description"]
	):
		events.append(
			{
				"name": f"holiday-{h.holiday_date}",
				"title": h.description,
				"start": str(h.holiday_date),
				"end": str(h.holiday_date),
				"allDay": 1,
				"convert_to_user_tz": 0,
				"display": "background",
				"color": "#f5b7b1",
			}
		)
	engineer = _engineer_filter(filters)
	if engineer:
		for lv in frappe.get_all(
			"HC Engineer Leave",
			filters={"engineer": engineer, "from_date": ["<=", end], "to_date": [">=", start]},
			fields=["name", "from_date", "to_date", "leave_type"],
		):
			events.append(
				{
					"name": lv.name,
					"title": _(lv.leave_type),
					"start": str(lv.from_date),
					"end": str(frappe.utils.add_days(lv.to_date, 1)),
					"allDay": 1,
					"convert_to_user_tz": 0,
					"display": "background",
					"color": "#d5d8dc",
				}
			)
	return events


@frappe.whitelist()
def update_event(args, field_map=None):
	"""Calendar drag & drop: book or reschedule the contract to the dropped day."""
	args = frappe._dict(json.loads(args) if isinstance(args, str) else args)
	if not args.name or str(args.name).startswith(("holiday-", "HCEL-")):
		frappe.throw(_("Holidays and leave cannot be moved here."))
	doc = frappe.get_doc("HC Contract", args.name)
	doc.check_permission("write")
	new_date = getdate(args.start)
	if doc.scheduled_date and doc.status in STATUS_COLORS:
		if getdate(doc.scheduled_date) == new_date:
			return
		doc.scheduled_date = new_date
		doc.reschedule_reason = "Changed in calendar"
	elif doc.status == "Not started":
		doc.scheduled_date = new_date
		doc.status = "Scheduled"
	else:
		frappe.throw(_("Only booked or not-started contracts can be moved."))
	doc.save()
	return doc.status
