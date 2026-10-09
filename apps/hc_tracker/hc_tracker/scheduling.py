"""Working days, holidays and engineer availability."""

import datetime as dt

import frappe
from frappe import _
from frappe.utils import add_days, cint, formatdate, getdate

from hc_tracker.utils import get_settings, split_list

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
BOOKED_STATUSES = ("Scheduled", "In progress")


def weekend_days() -> set[int]:
	names = split_list(get_settings().weekend_days or "Friday,Saturday")
	return {DAY_NAMES.index(n.lower()) for n in names if n.lower() in DAY_NAMES}


def skip_non_working_days() -> bool:
	return bool(cint(get_settings().skip_non_working_days))


def holiday_map() -> dict[dt.date, str]:
	cache = getattr(frappe.local, "hc_holiday_map", None)
	if cache is None:
		cache = {
			getdate(r.holiday_date): r.description
			for r in frappe.get_all("HC Holiday", fields=["holiday_date", "description"])
		}
		frappe.local.hc_holiday_map = cache
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


def check_availability(engineer: str | None, day, exclude_contract: str | None = None) -> list[dict]:
	"""Return problems for booking `engineer` on `day`: [{"kind", "message"}]."""
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
	leaves = frappe.get_all(
		"HC Engineer Leave",
		filters={"engineer": engineer, "from_date": ["<=", day], "to_date": [">=", day]},
		fields=["leave_type", "from_date", "to_date"],
	)
	for leave in leaves:
		problems.append(
			{
				"kind": "leave",
				"message": _("{0} is on {1} from {2} to {3}.").format(
					name, _(leave.leave_type).lower(), formatdate(leave.from_date), formatdate(leave.to_date)
				),
			}
		)
	filters = {"assigned_engineer": engineer, "scheduled_date": day, "status": ["in", BOOKED_STATUSES]}
	if exclude_contract:
		filters["name"] = ["!=", exclude_contract]
	for other in frappe.get_all("HC Contract", filters=filters, fields=["name", "client_name"]):
		problems.append(
			{
				"kind": "double_booking",
				"message": _("{0} already has the health check for {1} ({2}) on {3}.").format(
					name, other.client_name, other.name, formatdate(day)
				),
			}
		)
	return problems


@frappe.whitelist()
def get_availability(engineer: str | None = None, date: str | None = None, contract: str | None = None) -> dict:
	"""Used by the booking dialog: problems for that date + the engineer's other bookings that week."""
	problems = check_availability(engineer, date, contract)
	week = []
	if engineer and date:
		day = getdate(date)
		start = add_days(day, -day.weekday() - 1)  # Sunday-based week (Qatar)
		week = frappe.get_all(
			"HC Contract",
			filters={
				"assigned_engineer": engineer,
				"scheduled_date": ["between", [start, add_days(start, 6)]],
				"status": ["in", BOOKED_STATUSES],
			},
			fields=["name", "client_name", "scheduled_date"],
			order_by="scheduled_date asc",
		)
	return {
		"problems": problems,
		"blocking": bool(cint(get_settings().block_unavailable_booking)),
		"week": [{"contract": w.name, "client": w.client_name, "date": formatdate(w.scheduled_date)} for w in week],
	}
