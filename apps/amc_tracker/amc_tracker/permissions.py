"""Row-level permissions for AMC Tracker (wired through hooks.py).

Who sees what:
* System Manager, AMC Technical Manager, AMC Account Manager, AMC Helpdesk: every client, AMC and visit.
* AMC Engineer: the AMCs they are on (Engineers table or a PM Visit), those AMCs' clients, visits,
  contact logs and notification logs, and their own leave. They can edit only their own visits.

Frappe v16 note: a `has_permission` hook must return True to allow. Returning None or False denies access,
so every "no opinion" path below returns True explicitly and lets the role permissions decide.
"""

import frappe

from amc_tracker.utils import AMC_ROLES, ROLE_ENGINEER, sees_all, user_roles


def _engineer_amcs_sql(user: str) -> str:
	u = frappe.db.escape(user)
	return (
		f"(select e.`parent` from `tabAMC Engineer` e where e.`parenttype` = 'AMC' and e.`engineer` = {u}"
		f" union select v.`amc` from `tabPM Visit` v where v.`engineer` = {u})"
	)


def _engineer_amc_names(user: str) -> set[str]:
	names = set(frappe.get_all("AMC Engineer", filters={"parenttype": "AMC", "engineer": user}, pluck="parent"))
	names |= set(frappe.get_all("PM Visit", filters={"engineer": user}, pluck="amc"))
	return names


def _restricted(user: str) -> bool:
	"""True for users who only see their own AMCs (engineers without a see-all role)."""
	return not sees_all(user) and ROLE_ENGINEER in user_roles(user)


# ---------------------------------------------------------------------------
# AMC / Client
# ---------------------------------------------------------------------------


def amc_query(user=None, doctype=None):
	user = user or frappe.session.user
	if not _restricted(user):
		return ""
	return f"`tabAMC`.`name` in {_engineer_amcs_sql(user)}"


def amc_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _restricted(user) or ptype == "create" or doc.is_new():
		return True
	return doc.name in _engineer_amc_names(user)


def client_query(user=None, doctype=None):
	user = user or frappe.session.user
	if not _restricted(user):
		return ""
	return f"`tabClient`.`name` in (select a.`client` from `tabAMC` a where a.`name` in {_engineer_amcs_sql(user)})"


def client_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _restricted(user) or doc.is_new():
		return True
	if ptype not in ("read", "print", "email", "report", "select"):
		return False
	amcs = _engineer_amc_names(user)
	return bool(amcs) and bool(frappe.db.exists("AMC", {"client": doc.name, "name": ["in", list(amcs)]}))


# ---------------------------------------------------------------------------
# PM Visit: engineers see the visits of their AMCs, edit only their own
# ---------------------------------------------------------------------------


def pm_visit_query(user=None, doctype=None):
	user = user or frappe.session.user
	if not _restricted(user):
		return ""
	return f"`tabPM Visit`.`amc` in {_engineer_amcs_sql(user)}"


def pm_visit_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _restricted(user):
		return True
	if ptype in ("write", "submit", "cancel", "delete"):
		return doc.get("engineer") == user
	return doc.get("engineer") == user or doc.get("amc") in _engineer_amc_names(user)


# ---------------------------------------------------------------------------
# Documents linked to an AMC (contact log, notification log)
# ---------------------------------------------------------------------------


def _linked_amc_query(doctype: str, user=None):
	user = user or frappe.session.user
	if not _restricted(user):
		return ""
	return f"`tab{doctype}`.`amc` in {_engineer_amcs_sql(user)}"


def _linked_amc_has_permission(doc, user=None):
	user = user or frappe.session.user
	if not _restricted(user):
		return True
	if doc.is_new() and not doc.get("amc"):
		return True
	return doc.get("amc") in _engineer_amc_names(user)


def contact_log_query(user=None, doctype=None):
	return _linked_amc_query("Client Contact Log", user)


def contact_log_has_permission(doc, ptype=None, user=None, debug=False):
	return _linked_amc_has_permission(doc, user)


def notification_log_query(user=None, doctype=None):
	return _linked_amc_query("AMC Notification Log", user)


def notification_log_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if _restricted(user) and not doc.get("amc"):
		return False  # digests, to-do lists and summaries are not for engineers
	return _linked_amc_has_permission(doc, user)


# ---------------------------------------------------------------------------
# Engineer Leave: engineers see and edit only their own
# ---------------------------------------------------------------------------


def engineer_leave_query(user=None, doctype=None):
	user = user or frappe.session.user
	if not _restricted(user):
		return ""
	return f"`tabEngineer Leave`.`engineer` = {frappe.db.escape(user)}"


def engineer_leave_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if not _restricted(user):
		return True
	return doc.get("engineer") in (None, "", user)


# ---------------------------------------------------------------------------
# Apps screen
# ---------------------------------------------------------------------------


def has_app_permission():
	user = frappe.session.user
	if user == "Administrator":
		return True
	return bool(user_roles(user) & (set(AMC_ROLES) | {"System Manager"}))
