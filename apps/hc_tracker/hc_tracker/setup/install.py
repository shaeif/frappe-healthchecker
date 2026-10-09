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
	frappe.db.commit()


def after_migrate():
	create_roles()
	setup_settings()
	create_default_flows(only_if_none_exist=True)


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
