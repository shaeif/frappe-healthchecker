"""Install / migrate hooks."""

import frappe

from hc_tracker.setup.default_flows import create_default_flows
from hc_tracker.utils import HC_ROLES

TIME_ZONE = "Asia/Qatar"


def after_install():
	create_roles()
	set_system_time_zone()
	setup_settings()
	create_default_flows()
	seed_qatar_holidays()
	grant_data_import_permission()
	frappe.db.commit()


def after_migrate():
	create_roles()
	setup_settings()
	create_default_flows(only_if_none_exist=True)
	grant_data_import_permission()


def after_setup_wizard(args=None):
	"""The setup wizard writes the time zone picked in the browser; enforce Asia/Qatar."""
	set_system_time_zone()


def create_roles():
	for role in HC_ROLES:
		if frappe.db.exists("Role", role):
			continue
		doc = frappe.new_doc("Role")
		doc.role_name = role
		doc.desk_access = 1
		doc.insert(ignore_permissions=True)


def set_system_time_zone(time_zone: str = TIME_ZONE):
	frappe.db.set_single_value("System Settings", "time_zone", time_zone)
	frappe.clear_cache()


def setup_settings():
	"""Write first-install defaults once (renewal_alert_days is never empty after that)."""
	if frappe.db.get_single_value("HC Settings", "renewal_alert_days"):
		return
	settings = frappe.get_single("HC Settings")
	settings.renewal_alert_days = 60
	settings.enable_daily_digest = 1
	settings.enable_popup_notifications = 1
	set_v13_defaults(settings)
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)


def add_roles(user: str, roles):
	"""Grant roles to an existing user.

	bench --site <site> execute hc_tracker.setup.install.add_roles --kwargs '{"user": "a@b.com", "roles": "HC Engineer,HC Helpdesk"}'
	"""
	if isinstance(roles, str):
		roles = [r.strip() for r in roles.split(",") if r.strip()]
	doc = frappe.get_doc("User", user)
	doc.add_roles(*roles)
	frappe.db.commit()
	return frappe.get_roles(user)



V13_DEFAULTS = {
	"weekend_days": "Friday,Saturday",
	"skip_non_working_days": 1,
	"enable_helpdesk_todo": 1,
	"todo_horizon_days": 45,
	"client_reply_wait_days": 3,
	"management_summary_frequency": "Weekly",
	"notification_language": "English",
}


def set_v13_defaults(settings):
	"""Defaults for the v1.3 helpdesk settings (only fills empty values)."""
	for field, value in V13_DEFAULTS.items():
		if not settings.get(field):
			settings.set(field, value)


def _second_tuesday_of_february(year: int):
	import datetime as dt

	day = dt.date(year, 2, 1)
	while day.weekday() != 1:
		day += dt.timedelta(days=1)
	return day + dt.timedelta(days=7)


def seed_qatar_holidays(years=None):
	"""Fixed-date Qatar public holidays for this and next year. Eid holidays follow the lunar calendar and
	are announced each year: add them in HC Holiday."""
	import datetime as dt

	from frappe.utils import getdate, today

	this_year = getdate(today()).year
	for year in years or (this_year, this_year + 1):
		for day, description in (
			(_second_tuesday_of_february(year), "National Sport Day"),
			(dt.date(year, 12, 18), "Qatar National Day"),
		):
			if not frappe.db.exists("HC Holiday", str(day)):
				frappe.get_doc({"doctype": "HC Holiday", "holiday_date": day, "description": description}).insert(
					ignore_permissions=True
				)


def grant_data_import_permission(role: str = "HC Technical Manager"):
	"""Let Technical Managers use Data Import (Excel import of contracts)."""
	from frappe.permissions import add_permission, update_permission_property

	if frappe.db.exists("Custom DocPerm", {"parent": "Data Import", "role": role, "permlevel": 0}):
		return
	add_permission("Data Import", role, 0, "read")
	for ptype in ("write", "create", "delete"):
		update_permission_property("Data Import", role, 0, ptype, 1, validate=False)
