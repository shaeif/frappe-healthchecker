"""AMC Team page: the AMC Admin adds users and puts them in groups (AMC roles).

Frappe lets only a System Manager edit users. An AMC Admin gets this narrower tool instead: create desk users,
switch their AMC groups, keep the engineer profile (areas of expertise) in step and disable leavers. It never
touches other roles, so an AMC Admin cannot grant System Manager or change a System Manager's account.
"""

import frappe
from frappe import _
from frappe.utils import cint, validate_email_address

from amc_tracker.setup.install import TIME_ZONE
from amc_tracker.utils import (
	ROLE_ACCOUNT_MANAGER,
	ROLE_ADMIN,
	ROLE_ENGINEER,
	ROLE_HELPDESK,
	ROLE_TECHNICAL_MANAGER,
)

# Listed in the order the page shows them
GROUPS = [ROLE_ADMIN, ROLE_TECHNICAL_MANAGER, ROLE_ACCOUNT_MANAGER, ROLE_HELPDESK, ROLE_ENGINEER]
TEAM_ADMIN_ROLES = ("System Manager", ROLE_ADMIN)


def _only_team_admin():
	frappe.only_for(TEAM_ADMIN_ROLES)


def _is_system_manager(user: str) -> bool:
	return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def _guard_target(user: str):
	if user in ("Administrator", "Guest"):
		frappe.throw(_("{0} cannot be changed here.").format(user), frappe.PermissionError)
	if _is_system_manager(user) and not _is_system_manager(frappe.session.user):
		frappe.throw(_("Only a System Manager can change a System Manager's account."), frappe.PermissionError)


def _member(user: str) -> dict:
	u = frappe.db.get_value(
		"User", user, ["name", "full_name", "enabled", "mobile_no", "last_login", "user_type"], as_dict=True
	)
	roles = set(frappe.get_roles(user))
	engineer = frappe.db.get_value("Engineer", user, ["status"], as_dict=True)
	expertise = (
		frappe.get_all("Engineer Expertise", filters={"parenttype": "Engineer", "parent": user}, pluck="expertise", order_by="idx")
		if engineer
		else []
	)
	return {
		"user": u.name,
		"full_name": u.full_name,
		"enabled": u.enabled,
		"mobile_no": u.mobile_no,
		"last_login": u.last_login,
		"groups": [g for g in GROUPS if g in roles],
		"system_manager": "System Manager" in roles,
		"engineer_status": engineer.status if engineer else None,
		"expertise": expertise,
	}


@frappe.whitelist()
def get_team() -> dict:
	"""Everyone with an AMC group, plus desk users who are not in a group yet (so they can be added)."""
	_only_team_admin()
	users = frappe.get_all(
		"User",
		filters={"user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]},
		pluck="name",
		order_by="full_name asc",
	)
	members = [_member(u) for u in users]
	return {
		"groups": [{"role": g, "label": _(g)} for g in GROUPS],
		"expertise": frappe.get_all("Expertise", filters={"enabled": 1}, pluck="name", order_by="name"),
		"members": members,
		"me": frappe.session.user,
	}


@frappe.whitelist()
def save_member(
	email: str,
	full_name: str,
	groups,
	mobile_no: str | None = None,
	expertise=None,
	is_new=0,
	password: str | None = None,
	send_welcome_email=1,
) -> dict:
	"""Create a user or change their groups. Roles outside the AMC groups are left as they are."""
	_only_team_admin()
	email = (email or "").strip().lower()
	full_name = (full_name or "").strip()
	groups = frappe.parse_json(groups) if isinstance(groups, str) else (groups or [])
	expertise = frappe.parse_json(expertise) if isinstance(expertise, str) else (expertise or [])
	groups = [g for g in GROUPS if g in groups]
	if not validate_email_address(email):
		frappe.throw(_("Enter a valid email address."))
	if not full_name:
		frappe.throw(_("Enter the full name."))
	if not groups:
		frappe.throw(_("Choose at least one group."))
	if ROLE_ENGINEER in groups and not expertise:
		frappe.throw(_("Choose the engineer's areas of expertise."))

	first, _sep, last = full_name.partition(" ")
	if frappe.db.exists("User", email):
		if cint(is_new):
			frappe.throw(_("{0} already exists. Open it from the list to change its groups.").format(email))
		_guard_target(email)
		user = frappe.get_doc("User", email)
		user.first_name, user.last_name = first, last
		if mobile_no is not None:
			user.mobile_no = mobile_no
		user.flags.ignore_permissions = True
		user.save()
	else:
		user = frappe.new_doc("User")
		user.update(
			{
				"email": email,
				"first_name": first,
				"last_name": last,
				"mobile_no": mobile_no,
				"user_type": "System User",
				"time_zone": TIME_ZONE,
				"send_welcome_email": 0 if password else cint(send_welcome_email),
			}
		)
		user.flags.ignore_permissions = True
		user.insert()
	if password:
		from frappe.utils.password import update_password

		update_password(email, password)

	current = {g for g in GROUPS if g in frappe.get_roles(email)}
	if email == frappe.session.user and ROLE_ADMIN in current and ROLE_ADMIN not in groups and not _is_system_manager(email):
		frappe.throw(_("You cannot remove yourself from AMC Admin. Ask another admin."))
	_set_engineer_profile(email, ROLE_ENGINEER in groups, expertise, mobile_no)
	to_add = [g for g in groups if g not in current]
	to_remove = [g for g in current if g not in groups]
	user.reload()
	user.flags.ignore_permissions = True
	if to_add:
		user.add_roles(*to_add)
	if to_remove:
		user.remove_roles(*to_remove)
	return _member(email)


def _set_engineer_profile(email: str, is_engineer: bool, expertise: list, mobile_no: str | None):
	"""Engineers need an active profile (areas of expertise); leaving the group only deactivates it, so their
	past visits keep pointing at a real engineer."""
	exists = frappe.db.exists("Engineer", email)
	if not is_engineer:
		if exists and frappe.db.get_value("Engineer", email, "status") != "Inactive":
			doc = frappe.get_doc("Engineer", email)
			doc.status = "Inactive"
			doc.flags.ignore_permissions = True
			doc.save()
		return
	doc = frappe.get_doc("Engineer", email) if exists else frappe.new_doc("Engineer")
	if not exists:
		doc.user = email
	doc.status = "Active"
	if mobile_no:
		doc.mobile_no = mobile_no
	doc.set("expertise", [{"expertise": x} for x in expertise])
	doc.flags.ignore_permissions = True
	doc.save()


@frappe.whitelist()
def set_enabled(user: str, enabled) -> dict:
	"""Disable a leaver (they can no longer log in) or enable them again."""
	_only_team_admin()
	_guard_target(user)
	if user == frappe.session.user and not cint(enabled):
		frappe.throw(_("You cannot disable your own account."))
	doc = frappe.get_doc("User", user)
	doc.enabled = cint(enabled)
	doc.flags.ignore_permissions = True
	doc.save()
	if frappe.db.exists("Engineer", user) and not cint(enabled):
		frappe.db.set_value("Engineer", user, "status", "Inactive")
	return _member(user)
