"""Row-level permissions for HC Tracker (wired through hooks.py).

Frappe v16 note: a `has_permission` hook must return True to allow. Returning None or False
denies access, so every "no opinion" path below returns True explicitly and lets the role
permissions in the DocType JSON decide.
"""

import frappe

from hc_tracker.utils import (
	FULL_ACCESS_ROLES,
	HC_ROLES,
	ROLE_ACCOUNT_MANAGER,
	ROLE_ENGINEER,
	ROLE_HELPDESK,
	user_roles,
)


def _sees_everything(user: str, roles: set[str]) -> bool:
	return user == "Administrator" or bool(roles & FULL_ACCESS_ROLES) or ROLE_HELPDESK in roles


def _own_contract_condition(user: str, roles: set[str], table: str) -> str:
	escaped = frappe.db.escape(user)
	conditions = []
	if ROLE_ACCOUNT_MANAGER in roles:
		conditions.append(f"{table}.`account_manager` = {escaped}")
	if ROLE_ENGINEER in roles:
		conditions.append(f"{table}.`assigned_engineer` = {escaped}")
	if not conditions:
		return "1=0"
	return "(" + " or ".join(conditions) + ")"


def _owns_contract(user: str, roles: set[str], account_manager: str | None, engineer: str | None) -> bool:
	if ROLE_ACCOUNT_MANAGER in roles and account_manager == user:
		return True
	if ROLE_ENGINEER in roles and engineer == user:
		return True
	return False


# ---------------------------------------------------------------------------
# HC Contract
# ---------------------------------------------------------------------------


def hc_contract_query(user=None, doctype=None):
	user = user or frappe.session.user
	roles = user_roles(user)
	if _sees_everything(user, roles):
		return ""
	return _own_contract_condition(user, roles, "`tabHC Contract`")


def hc_contract_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	roles = user_roles(user)
	if _sees_everything(user, roles):
		# Helpdesk field-level restrictions are enforced in HCContract.validate()
		return True
	if ptype == "create" or doc.is_new():
		# Creation is governed purely by role permissions (Account Managers may create)
		return True
	return _owns_contract(user, roles, doc.get("account_manager"), doc.get("assigned_engineer"))


# ---------------------------------------------------------------------------
# HC Notification Log
# ---------------------------------------------------------------------------


def hc_notification_log_query(user=None, doctype=None):
	user = user or frappe.session.user
	roles = user_roles(user)
	if _sees_everything(user, roles):
		return ""
	condition = _own_contract_condition(user, roles, "c")
	if condition == "1=0":
		return "1=0"
	return (
		"`tabHC Notification Log`.`contract` in "
		f"(select c.`name` from `tabHC Contract` c where {condition})"
	)


def hc_notification_log_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	roles = user_roles(user)
	if _sees_everything(user, roles):
		return True
	if not doc.get("contract"):
		return False
	values = frappe.db.get_value(
		"HC Contract", doc.contract, ["account_manager", "assigned_engineer"], as_dict=True
	)
	if not values:
		return False
	return _owns_contract(user, roles, values.account_manager, values.assigned_engineer)


# ---------------------------------------------------------------------------
# Apps screen
# ---------------------------------------------------------------------------


def has_app_permission():
	user = frappe.session.user
	if user == "Administrator":
		return True
	roles = user_roles(user)
	return bool(roles & (set(HC_ROLES) | {"System Manager"}))
