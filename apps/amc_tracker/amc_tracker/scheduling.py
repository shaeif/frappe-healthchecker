"""Working days, holidays and engineer availability."""

import datetime as dt

import frappe
from frappe import _
from frappe.utils import add_days, cint, formatdate, getdate

from amc_tracker.utils import get_settings, split_list

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
BUSY_STATUSES = ("Scheduled", "Completed", "Report submitted")


def weekend_days() -> set[int]:
	names = split_list(get_settings().weekend_days or "Friday,Saturday")
	return {DAY_NAMES.index(n.lower()) for n in names if n.lower() in DAY_NAMES}


def skip_non_working_days() -> bool:
	return bool(cint(get_settings().skip_non_working_days))


def holiday_map() -> dict[dt.date, str]:
	cache = getattr(frappe.local, "amc_holiday_map", None)
	if cache is None:
		cache = {
			getdate(r.holiday_date): r.description
			for r in frappe.get_all("Public Holiday", fields=["holiday_date", "description"])
		}
		frappe.local.amc_holiday_map = cache
	return cache


def non_working_reason(day) -> str | None:
	day = getdate(day)
	if day in holiday_map():
		return _("public holiday ({0})").format(holiday_map()[day])
	if day.weekday() in weekend_days():
		return _("weekend ({0})").format(_(DAY_NAMES[day.weekday()].capitalize()))
	return None


def is_working_day(day) -> bool:
	return non_working_reason(day) is None


def shift_to_working_day(day, direction: int):
	"""Move `day` to the nearest working day: direction -1 = earlier, +1 = later."""
	day = getdate(day)
	for _i in range(60):
		if is_working_day(day):
			return day
		day = add_days(day, direction)
	return day


def next_working_days(start, count: int) -> list:
	days, day = [], getdate(start)
	while len(days) < count:
		day = add_days(day, 1)
		if is_working_day(day):
			days.append(getdate(day))
	return days


# ---------------------------------------------------------------------------
# Engineer availability
# ---------------------------------------------------------------------------


def check_availability(engineer: str | None, day, exclude_visit: str | None = None) -> list[dict]:
	"""Problems with planning `engineer` on `day`: [{"kind", "message"}]."""
	problems = []
	if not day:
		return problems
	day = getdate(day)
	reason = non_working_reason(day)
	if reason:
		problems.append({"kind": "non_working_day", "message": _("{0} is a {1}.").format(formatdate(day), reason)})
	if not engineer:
		return problems

	name = frappe.db.get_value("User", engineer, "full_name") or engineer
	for leave in frappe.get_all(
		"Engineer Leave",
		filters={"engineer": engineer, "from_date": ["<=", day], "to_date": [">=", day]},
		fields=["leave_type", "from_date", "to_date"],
	):
		problems.append(
			{
				"kind": "leave",
				"message": _("{0} is on {1} from {2} to {3}.").format(
					name, _(leave.leave_type).lower(), formatdate(leave.from_date), formatdate(leave.to_date)
				),
			}
		)
	filters = {"engineer": engineer, "visit_date": day, "status": ["in", BUSY_STATUSES]}
	if exclude_visit:
		filters["name"] = ["!=", exclude_visit]
	for other in frappe.get_all("PM Visit", filters=filters, fields=["name", "client_name", "visit_mode"]):
		problems.append(
			{
				"kind": "double_booking",
				"message": _("{0} already has a PM visit for {1} ({2}) on {3}.").format(
					name, other.client_name, _(other.visit_mode or ""), formatdate(day)
				),
			}
		)
	return problems


@frappe.whitelist()
def get_availability(engineer: str | None = None, date: str | None = None, visit: str | None = None) -> dict:
	"""Used by the visit date dialog: problems for that date + the engineer's other visits that week."""
	problems = check_availability(engineer, date, visit)
	week = []
	if engineer and date:
		day = getdate(date)
		start = add_days(day, -((day.weekday() + 1) % 7))  # Sunday-based week (Qatar)
		filters = {
			"engineer": engineer,
			"visit_date": ["between", [start, add_days(start, 6)]],
			"status": ["in", BUSY_STATUSES],
		}
		if visit:
			filters["name"] = ["!=", visit]
		week = frappe.get_all(
			"PM Visit", filters=filters, fields=["name", "client_name", "visit_date", "visit_mode"], order_by="visit_date asc"
		)
	return {
		"problems": problems,
		"blocking": bool(cint(get_settings().block_unavailable_booking)),
		"week": [
			{"visit": w.name, "client": w.client_name, "date": formatdate(w.visit_date), "mode": _(w.visit_mode or "")}
			for w in week
		],
	}
