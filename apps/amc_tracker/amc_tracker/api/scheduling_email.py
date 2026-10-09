"""Client scheduling emails (logged as a Communication on the AMC / PM Visit and as a Client Contact Log)."""

import frappe
from frappe import _
from frappe.utils import formatdate, now_datetime

from amc_tracker.notifications import templates as tpl
from amc_tracker.utils import get_settings, split_list


def _docs(amc: str, visit: str | None):
	amc_doc = frappe.get_doc("AMC", amc)
	visit_doc = frappe.get_doc("PM Visit", visit) if visit else None
	if visit_doc and visit_doc.amc != amc_doc.name:
		frappe.throw(_("PM Visit {0} belongs to another AMC.").format(visit))
	client = frappe.get_doc("Client", amc_doc.client)
	return amc_doc, visit_doc, client


@frappe.whitelist()
def get_scheduling_email(amc: str, visit: str | None = None, proposed_dates=None) -> dict:
	"""Pre-filled email to the client (AMC Settings template or the default, in the notification language)."""
	amc_doc, visit_doc, client = _docs(amc, visit)
	(visit_doc or amc_doc).check_permission("read")
	if isinstance(proposed_dates, str):
		proposed_dates = frappe.parse_json(proposed_dates)
	ctx = {
		"doc": amc_doc,
		"amc": amc_doc,
		"client": client,
		"visit": visit_doc,
		"proposed_dates": [formatdate(d) for d in proposed_dates or [] if d],
		"due_date": formatdate(amc_doc.next_due_date) if amc_doc.next_due_date else "",
		"sender_name": frappe.utils.get_fullname(frappe.session.user),
	}
	settings = get_settings()
	language = settings.notification_language or "English"

	def render(template, default):
		return frappe.render_template(template or default, ctx)

	en_subject = render(settings.scheduling_email_subject, tpl.SCHEDULING_EMAIL_SUBJECT)
	en_message = render(settings.scheduling_email_template, tpl.SCHEDULING_EMAIL_MESSAGE)
	ar_subject = render(None, tpl.SCHEDULING_EMAIL_SUBJECT_AR)
	ar_message = render(None, tpl.SCHEDULING_EMAIL_MESSAGE_AR)
	if language == "Arabic":
		subject, message = ar_subject, tpl.rtl(ar_message)
	elif language == "English + Arabic":
		subject, message = f"{en_subject} | {ar_subject}", tpl.bilingual(en_message, ar_message)
	else:
		subject, message = en_subject, en_message
	cc = split_list(client.cc_emails)
	if visit_doc:
		cc.append(frappe.db.get_value("User", visit_doc.engineer, "email"))
	if settings.default_helpdesk_email:
		cc.append(settings.default_helpdesk_email)
	return {
		"recipients": client.contact_email or "",
		"cc": ", ".join(dict.fromkeys(c for c in cc if c)),
		"subject": subject.strip(),
		"message": message,
	}


@frappe.whitelist()
def send_scheduling_email(
	amc: str, recipients: str, subject: str, message: str, cc: str | None = None, visit: str | None = None
) -> str:
	"""Send through the Email Queue, linked to the visit (or AMC) so client replies thread to it."""
	from frappe.core.doctype.communication.email import make

	amc_doc, visit_doc, _client = _docs(amc, visit)
	(visit_doc or amc_doc).check_permission("email" if not visit_doc else "write")
	if not recipients:
		frappe.throw(_("Enter the client email address."))
	for address in split_list(recipients) + split_list(cc):
		frappe.utils.validate_email_address(address, throw=True)
	ref_doctype, ref_name = ("PM Visit", visit_doc.name) if visit_doc else ("AMC", amc_doc.name)
	result = make(
		doctype=ref_doctype,
		name=ref_name,
		content=message,
		subject=subject,
		recipients=recipients,
		cc=cc or None,
		send_email=True,
		communication_medium="Email",
	)
	log = frappe.new_doc("Client Contact Log")
	log.update(
		{
			"amc": amc_doc.name,
			"pm_visit": visit_doc.name if visit_doc else None,
			"contact_on": now_datetime(),
			"method": "Email",
			"direction": "Outgoing",
			"outcome": "Scheduling email sent",
			"notes": subject,
		}
	)
	log.insert(ignore_permissions=True)
	return result.get("name") if isinstance(result, dict) else ""
