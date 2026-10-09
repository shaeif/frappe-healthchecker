"""Delivery channels: Email (Email Queue / Office 365 SMTP), Microsoft Teams (Workflows webhook,
Adaptive Card) and System Notification (bell entry + real-time on-screen pop-up)."""

import re

import frappe
from frappe import _
from frappe.utils import cint, get_url_to_form, strip_html

TEAMS_TIMEOUT_SECONDS = 15
POPUP_EVENT = "hc_tracker_popup"


class DeliveryError(Exception):
	"""Raised when a channel cannot deliver; the message is stored in the notification log."""


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def send_email(recipients: list[str], cc: list[str], subject: str, message: str, reference_name=None):
	"""Queue an email. The Email Queue worker sends it through the default outgoing Email Account."""
	recipients = [r for r in recipients if r]
	cc = [c for c in cc if c and c not in recipients]
	if not recipients and cc:
		recipients, cc = cc, []
	if not recipients:
		raise DeliveryError(_("No email recipients resolved"))

	try:
		frappe.sendmail(
			recipients=recipients,
			cc=cc or None,
			subject=subject,
			message=message,
			reference_doctype="HC Contract" if reference_name else None,
			reference_name=reference_name,
			delayed=True,
		)
	except frappe.OutgoingEmailError:
		# Do not show Frappe's message to the user who triggered the save; it is logged instead
		frappe.clear_last_message()
		raise DeliveryError(
			_("No default outgoing Email Account. Configure the Office 365 Email Account (Default Outgoing).")
		)


# ---------------------------------------------------------------------------
# Microsoft Teams (Workflows "When a Teams webhook request is received")
# ---------------------------------------------------------------------------


def html_to_text(html: str | None) -> str:
	"""Convert simple HTML to text that renders well inside an Adaptive Card TextBlock."""
	if not html:
		return ""
	text = re.sub(r"(?i)<br\s*/?>", "\n", html)
	text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", text)
	text = re.sub(r"(?i)<li[^>]*>", "- ", text)
	text = strip_html(text)
	text = re.sub(r"[ \t]+", " ", text)
	lines = [line.strip() for line in text.splitlines()]
	text = "\n".join(lines)
	text = re.sub(r"\n{3,}", "\n\n", text).strip()
	# Teams TextBlocks need a blank line to render a line break reliably
	return text.replace("\n", "\n\n").replace("\n\n\n\n", "\n\n")


def build_adaptive_card(
	title: str,
	text: str = "",
	facts: list[tuple[str, str]] | None = None,
	url: str | None = None,
	url_title: str | None = None,
	color: str = "Accent",
) -> dict:
	"""Message payload accepted by the Teams Workflows webhook (Adaptive Card 1.4)."""
	body = [
		{
			"type": "TextBlock",
			"text": title,
			"weight": "Bolder",
			"size": "Medium",
			"wrap": True,
			"color": color,
		}
	]
	if text:
		body.append({"type": "TextBlock", "text": text, "wrap": True})
	if facts:
		body.append(
			{
				"type": "FactSet",
				"facts": [{"title": str(k), "value": str(v if v not in (None, "") else "-")} for k, v in facts],
			}
		)

	card = {
		"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
		"type": "AdaptiveCard",
		"version": "1.4",
		"body": body,
		"msteams": {"width": "Full"},
	}
	if url:
		card["actions"] = [{"type": "Action.OpenUrl", "title": url_title or _("Open in HC Tracker"), "url": url}]

	return {
		"type": "message",
		"attachments": [
			{
				"contentType": "application/vnd.microsoft.card.adaptive",
				"contentUrl": None,
				"content": card,
			}
		],
	}


def post_to_teams(webhook_url: str | None, payload: dict):
	import requests

	if not webhook_url:
		raise DeliveryError(_("No Teams webhook URL configured (step or HC Settings)"))

	response = requests.post(webhook_url.strip(), json=payload, timeout=TEAMS_TIMEOUT_SECONDS)
	# Workflows webhooks answer 202 Accepted; legacy endpoints answer 200
	if response.status_code >= 300:
		raise DeliveryError(
			_("Teams webhook returned HTTP {0}: {1}").format(response.status_code, (response.text or "")[:500])
		)


# ---------------------------------------------------------------------------
# System Notification: bell entry (Notification Log) + real-time pop-up
# ---------------------------------------------------------------------------


def send_system_notification(
	users: list[str],
	subject: str,
	message: str,
	contract_name: str | None = None,
	indicator: str = "blue",
):
	"""Create a bell notification for each user and push an on-screen pop-up to their open sessions.

	Uses Notification Type "Alert", which Frappe never emails on its own, so the user does not
	get a duplicate of the HC email.
	"""
	users = [u for u in dict.fromkeys(users) if u and u not in ("Guest",)]
	if not users:
		raise DeliveryError(_("No system users to notify"))

	route = ["Form", "HC Contract", contract_name] if contract_name else None
	url = get_url_to_form("HC Contract", contract_name) if contract_name else None
	for user in users:
		log = frappe.new_doc("Notification Log")
		log.update(
			{
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"email_content": message,
				"document_type": "HC Contract" if contract_name else None,
				"document_name": contract_name,
			}
		)
		log.insert(ignore_permissions=True)

		frappe.publish_realtime(
			POPUP_EVENT,
			message={
				"title": subject,
				"message": message,
				"indicator": indicator,
				"route": route,
				"url": url,
				"contract": contract_name,
			},
			user=user,
			after_commit=True,
		)


def users_only(entries: list[dict]) -> list[str]:
	return [e["user"] for e in entries if e.get("user")]


def emails_only(entries: list[dict]) -> list[str]:
	return [e["email"] for e in entries if e.get("email")]


def is_true(value) -> bool:
	return bool(cint(value))
