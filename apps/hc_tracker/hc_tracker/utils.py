"""Shared helpers for HC Tracker."""

import re

import frappe
from frappe.utils import cint, getdate, today

FREQUENCY_MONTHS = {
	"Monthly": 1,
	"Quarterly": 3,
	"Half-yearly": 6,
	"Yearly": 12,
}

STATUSES = ["Not started", "Scheduled", "In progress", "Report sent", "Signed off"]

ROLE_HELPDESK = "HC Helpdesk"
ROLE_ENGINEER = "HC Engineer"
ROLE_ACCOUNT_MANAGER = "HC Account Manager"
ROLE_TECHNICAL_MANAGER = "HC Technical Manager"
HC_ROLES = [ROLE_HELPDESK, ROLE_ENGINEER, ROLE_ACCOUNT_MANAGER, ROLE_TECHNICAL_MANAGER]

# Roles with unrestricted access to contracts, flows and settings
FULL_ACCESS_ROLES = {"System Manager", ROLE_TECHNICAL_MANAGER}
# Roles allowed to set status "Signed off"
SIGN_OFF_ROLES = {"System Manager", ROLE_TECHNICAL_MANAGER, ROLE_ACCOUNT_MANAGER}

# User (Link) fields of HC Contract that a notification step may target
CONTRACT_USER_FIELDS = ["assigned_engineer", "account_manager", "helpdesk_contact", "technical_manager"]


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
	return frappe.get_cached_doc("HC Settings")


def user_roles(user: str | None = None) -> set[str]:
	return set(frappe.get_roles(user or frappe.session.user))


def is_full_access(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(user_roles(user) & FULL_ACCESS_ROLES)


def can_sign_off(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(user_roles(user) & SIGN_OFF_ROLES)


def popups_enabled() -> bool:
	return bool(cint(get_settings().enable_popup_notifications))


def teams_enabled() -> bool:
	return bool(cint(get_settings().enable_teams))
