"""Client booking request emails (logged as a Communication on the contract and as an HC Contact Log)."""

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, now_datetime

from hc_tracker.notifications import templates as tpl
from hc_tracker.utils import get_settings, split_list


def _context(doc, proposed_dates):
	return {
		"doc": doc,
		"proposed_dates": [formatdate(d) for d in proposed_dates if d],
		"due_date": formatdate(doc.next_due_date) if doc.next_due_date else "",
		"sender_name": frappe.utils.get_fullname(frappe.session.user),
	}


@frappe.whitelist()
def get_booking_request(contract: str, proposed_dates=None) -> dict:
	"""Pre-filled booking request email (HC Settings template or the default, in the notification language)."""
	doc = frappe.get_doc("HC Contract", contract)
	doc.check_permission("read")
	if isinstance(proposed_dates, str):
		proposed_dates = frappe.parse_json(proposed_dates)
	ctx = _context(doc, proposed_dates or [])
	settings = get_settings()
	language = settings.notification_language or "English"

	def render(template, default):
		return frappe.render_template(template or default, ctx)

	en_subject = render(settings.booking_request_subject, tpl.BOOKING_REQUEST_SUBJECT)
	en_message = render(settings.booking_request_template, tpl.BOOKING_REQUEST_MESSAGE)
	ar_subject = render(None, tpl.BOOKING_REQUEST_SUBJECT_AR)
	ar_message = render(None, tpl.BOOKING_REQUEST_MESSAGE_AR)
	if language == "Arabic":
		subject, message = ar_subject, tpl.rtl(ar_message)
	elif language == "English + Arabic":
		subject, message = f"{en_subject} | {ar_subject}", tpl.bilingual(en_message, ar_message)
	else:
		subject, message = en_subject, en_message
	cc = split_list(doc.client_cc_emails)
	if settings.default_helpdesk_email:
		cc.append(settings.default_helpdesk_email)
	return {
		"recipients": doc.client_contact_email or "",
		"cc": ", ".join(dict.fromkeys(cc)),
		"subject": subject.strip(),
		"message": message,
	}


@frappe.whitelist()
def send_booking_request(contract: str, recipients: str, subject: str, message: str, cc: str | None = None) -> str:
	"""Send the email to the client through the Email Queue, linked to the contract (replies thread to it)."""
	from frappe.core.doctype.communication.email import make

	doc = frappe.get_doc("HC Contract", contract)
	doc.check_permission("email")
	if not recipients:
		frappe.throw(_("Enter the client email address."))
	for address in split_list(recipients) + split_list(cc):
		frappe.utils.validate_email_address(address, throw=True)
	result = make(
		doctype="HC Contract",
		name=contract,
		content=message,
		subject=subject,
		recipients=recipients,
		cc=cc or None,
		send_email=True,
		communication_medium="Email",
	)
	log = frappe.new_doc("HC Contact Log")
	log.update(
		{
			"contract": contract,
			"contact_on": now_datetime(),
			"method": "Email",
			"direction": "Outgoing",
			"outcome": "Booking request sent",
			"notes": subject,
		}
	)
	log.insert(ignore_permissions=True)
	return result.get("name") if isinstance(result, dict) else ""
