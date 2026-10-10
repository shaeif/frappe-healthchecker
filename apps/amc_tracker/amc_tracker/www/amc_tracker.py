"""Apps-screen entry point: open the workspace this user can see.

The AMC Tracker workspace is for managers and the helpdesk; engineers only have My Work. Opening a workspace you
cannot see makes the desk look it up as a Page instead ("No permission for Page"), so route by role here.
"""

import frappe

from amc_tracker.utils import user_roles

no_cache = 1

ROUTE = "/amc-tracker"


def get_context(context):
	user = frappe.session.user
	if user == "Guest":
		target = f"/login?redirect-to={ROUTE}"
	else:
		workspace_roles = {r.role for r in frappe.get_cached_doc("Workspace", "AMC Tracker").roles}
		if user == "Administrator" or not workspace_roles or user_roles(user) & workspace_roles:
			target = "/desk/amc-tracker"
		else:
			target = "/desk/my-work"
	frappe.local.flags.redirect_location = target
	raise frappe.Redirect(302)  # per user, so browsers must not cache it
