"""Whitelisted helper actions used by form buttons."""

import frappe
from frappe import _
from frappe.utils import get_url

from amc_tracker.notifications import channels as ch
from amc_tracker.utils import get_settings

MANAGER_ROLES = ("System Manager", "AMC Technical Manager")


@frappe.whitelist()
def send_test_teams_message(webhook_url: str | None = None):
	"""Post a test Adaptive Card to the given webhook (or AMC Settings default)."""
	frappe.only_for(MANAGER_ROLES)
	settings = get_settings()
	url = (webhook_url or settings.default_teams_webhook_url or "").strip()
	payload = ch.build_adaptive_card(
		_("AMC Tracker test message"),
		_("If you can read this card, the Teams Workflows webhook is configured correctly."),
		[(_("Site"), get_url()), (_("Sent by"), frappe.session.user)],
		url=get_url("/desk/amc-tracker"),
	)
	try:
		ch.post_to_teams(url, payload)
	except ch.DeliveryError as e:
		frappe.throw(str(e), title=_("Teams test failed"))
	return _("Test card posted to Teams.")


@frappe.whitelist()
def send_test_popup():
	"""Show a test pop-up + bell notification to the current user."""
	ch.send_system_notification(
		[frappe.session.user],
		_("AMC Tracker test pop-up"),
		_("<p>Pop-up notifications are working for <b>{0}</b>.</p>").format(frappe.session.user),
		indicator="green",
	)
	return _("Test pop-up sent. It appears in a moment and in the bell icon.")


@frappe.whitelist()
def send_test_email(recipient: str | None = None):
	"""Send a test email through the default outgoing Email Account (Office 365)."""
	frappe.only_for(MANAGER_ROLES)
	recipient = recipient or frappe.session.user
	frappe.sendmail(
		recipients=[recipient],
		subject=_("AMC Tracker test email"),
		message=_("<p>Outgoing email from AMC Tracker works.</p>"),
		now=True,
	)
	return _("Test email sent to {0}.").format(recipient)
