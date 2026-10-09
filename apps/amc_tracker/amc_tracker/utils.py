"""Shared constants and helpers for AMC Tracker."""

import re

import frappe
from frappe.utils import cint, getdate, today

FREQUENCY_MONTHS = {
	"Monthly": 1,
	"Quarterly": 3,
	"Half-yearly": 6,
	"Yearly": 12,
}

# Status of the current PM cycle of an AMC (derived from its PM Visits, except "Signed off")
CYCLE_NOT_STARTED = "Not started"
CYCLE_ASSIGNED = "Engineers assigned"
CYCLE_SCHEDULED = "Scheduled"
CYCLE_IN_PROGRESS = "In progress"
CYCLE_REPORTS = "Reports submitted"
CYCLE_SIGNED_OFF = "Signed off"
CYCLE_STATUSES = [CYCLE_NOT_STARTED, CYCLE_ASSIGNED, CYCLE_SCHEDULED, CYCLE_IN_PROGRESS, CYCLE_REPORTS, CYCLE_SIGNED_OFF]

# Status of one PM Visit
VISIT_TO_SCHEDULE = "To be scheduled"
VISIT_SCHEDULED = "Scheduled"
VISIT_COMPLETED = "Completed"
VISIT_REPORTED = "Report submitted"
VISIT_CANCELLED = "Cancelled"
VISIT_OPEN = (VISIT_TO_SCHEDULE, VISIT_SCHEDULED, VISIT_COMPLETED)

ROLE_HELPDESK = "AMC Helpdesk"
ROLE_ENGINEER = "AMC Engineer"
ROLE_ACCOUNT_MANAGER = "AMC Account Manager"
ROLE_TECHNICAL_MANAGER = "AMC Technical Manager"
AMC_ROLES = [ROLE_HELPDESK, ROLE_ENGINEER, ROLE_ACCOUNT_MANAGER, ROLE_TECHNICAL_MANAGER]

# Roles with unrestricted access to clients, AMCs, notification rules and settings
FULL_ACCESS_ROLES = {"System Manager", ROLE_TECHNICAL_MANAGER}
# Roles that see every client / AMC / visit (engineers only see the AMCs they are assigned to)
SEE_ALL_ROLES = FULL_ACCESS_ROLES | {ROLE_HELPDESK, ROLE_ACCOUNT_MANAGER}
# Roles allowed to sign off a PM cycle
SIGN_OFF_ROLES = {"System Manager", ROLE_TECHNICAL_MANAGER, ROLE_ACCOUNT_MANAGER}
# Roles that assign engineers to an AMC / PM cycle
ASSIGN_ROLES = {"System Manager", ROLE_TECHNICAL_MANAGER, ROLE_HELPDESK}

# User (Link) fields of AMC that a notification step may target ("AMC Field" recipient type)
AMC_USER_FIELDS = ["account_manager", "technical_manager", "helpdesk_contact"]


def get_interval_months(frequency: str | None) -> int:
	return FREQUENCY_MONTHS.get(frequency or "", 0)


def get_period_label(due_date, frequency: str | None) -> str:
	"""Cycle label derived from the due date: 2026-10 / 2026-Q4 / 2026-H2 / 2026."""
	if not due_date:
		return ""
	d = getdate(due_date)
	if frequency == "Monthly":
		return f"{d.year}-{d.month:02d}"
	if frequency == "Quarterly":
		return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
	if frequency == "Half-yearly":
		return f"{d.year}-H{1 if d.month <= 6 else 2}"
	return str(d.year)


def split_list(value: str | None) -> list[str]:
	"""Split a comma / semicolon / newline separated string into clean, unique items."""
	if not value:
		return []
	items = []
	for part in re.split(r"[,;\n]", value):
		part = part.strip()
		if part and part not in items:
			items.append(part)
	return items


def get_today(on_date=None):
	"""Today's date in the system time zone, or the simulated date passed in."""
	return getdate(on_date) if on_date else getdate(today())


def get_settings():
	return frappe.get_cached_doc("AMC Settings")


def user_roles(user: str | None = None) -> set[str]:
	return set(frappe.get_roles(user or frappe.session.user))


def is_full_access(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(user_roles(user) & FULL_ACCESS_ROLES)


def sees_all(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(user_roles(user) & SEE_ALL_ROLES)


def can_sign_off(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(user_roles(user) & SIGN_OFF_ROLES)


def can_assign(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(user_roles(user) & ASSIGN_ROLES)


def full_name(user: str | None) -> str:
	if not user:
		return ""
	return frappe.db.get_value("User", user, "full_name") or user


def popups_enabled() -> bool:
	return bool(cint(get_settings().enable_popup_notifications))


def teams_enabled() -> bool:
	return bool(cint(get_settings().enable_teams))
