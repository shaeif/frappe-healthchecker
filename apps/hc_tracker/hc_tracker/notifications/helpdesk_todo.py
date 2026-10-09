"""Helpdesk daily to-do: what the helpdesk must do today (email + pop-up each working morning, and the
"Helpdesk To-Do" report)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, escape_html, formatdate, get_datetime, get_url_to_form, getdate

from hc_tracker.notifications import channels as ch
from hc_tracker.notifications import templates as tpl
from hc_tracker.notifications.engine import CH_EMAIL, CH_SYSTEM, _value_entry, users_with_role, write_log
from hc_tracker.scheduling import next_working_days
from hc_tracker.utils import ROLE_HELPDESK, get_settings, get_today

TODO_LABEL = "Helpdesk daily to-do"

SECTIONS = [
	("follow_up", "Follow-ups due today", "متابعات مستحقة اليوم"),
	("awaiting_reply", "Awaiting client reply", "بانتظار رد العميل"),
	("book_now", "Book now (not booked yet)", "احجز الآن (لم يُحجز بعد)"),
	("confirm", "Confirm with client (booked in the next 2 working days)", "تأكيد مع العميل (محجوز خلال يومي عمل)"),
	("overdue", "Overdue", "متأخر"),
]


def _open_contracts():
	return frappe.get_all(
		"HC Contract",
		filters={"status": ["!=", "Signed off"], "next_due_date": ["is", "set"]},
		fields=[
			"name", "client_name", "next_due_date", "scheduled_date", "status", "assigned_engineer", "engineer_name",
			"client_contact_name", "client_contact_phone", "client_contact_email", "reminders_paused_until",
			"booking_request_sent_on", "last_contact_on", "last_contact_outcome", "contract_end",
		],
		order_by="next_due_date asc",
	)


def build_todo(on_date=None) -> dict[str, list[dict]]:
	on_date = get_today(on_date)
	settings = get_settings()
	horizon = cint(settings.todo_horizon_days) or 45
	wait_days = cint(settings.client_reply_wait_days) or 3
	confirm_days = set(next_working_days(on_date, 2))
	todo = {key: [] for key, _en, _ar in SECTIONS}
	seen = set()

	# Follow-ups from the contact log (latest log per contract with follow_up_on <= today)
	logs = frappe.get_all(
		"HC Contact Log",
		filters={"follow_up_on": ["<=", on_date]},
		fields=["name", "contract", "follow_up_on", "outcome", "notes", "contact_on"],
		order_by="contact_on desc",
	)
	latest = {}
	for log in frappe.get_all("HC Contact Log", fields=["contract", "name"], order_by="contact_on desc"):
		latest.setdefault(log.contract, log.name)

	contracts = {c.name: c for c in _open_contracts() if not c.contract_end or getdate(c.contract_end) >= on_date}
	for log in logs:
		c = contracts.get(log.contract)
		if not c or latest.get(log.contract) != log.name or c.status != "Not started":
			continue
		todo["follow_up"].append(_row(c, on_date, _("{0} on {1}: {2}").format(_(log.outcome), formatdate(log.contact_on), log.notes or "")))
		seen.add(c.name)

	for c in contracts.values():
		due = getdate(c.next_due_date)
		days_left = date_diff(due, on_date)
		if c.status == "Not started" and c.name not in seen:
			paused = c.reminders_paused_until and getdate(c.reminders_paused_until) > on_date
			if c.booking_request_sent_on and date_diff(on_date, get_datetime(c.booking_request_sent_on)) >= wait_days:
				todo["awaiting_reply"].append(
					_row(c, on_date, _("Booking request sent on {0}").format(formatdate(c.booking_request_sent_on)))
				)
			elif not c.booking_request_sent_on and not paused and days_left <= horizon and days_left >= 0:
				todo["book_now"].append(_row(c, on_date, _("Due in {0} days").format(days_left)))
		if c.status == "Scheduled" and c.scheduled_date and getdate(c.scheduled_date) in confirm_days:
			todo["confirm"].append(_row(c, on_date, _("Booked for {0}").format(formatdate(c.scheduled_date))))
		if days_left < 0:
			todo["overdue"].append(_row(c, on_date, _("Overdue by {0} days").format(-days_left)))
	return todo


def _row(c, on_date, detail) -> dict:
	return {
		"contract": c.name,
		"client": c.client_name,
		"due_date": c.next_due_date,
		"status": c.status,
		"engineer": c.engineer_name or c.assigned_engineer or "",
		"contact": " / ".join(x for x in (c.client_contact_name, c.client_contact_phone, c.client_contact_email) if x),
		"last_contact": f"{_(c.last_contact_outcome)} ({formatdate(c.last_contact_on)})" if c.last_contact_on else "",
		"detail": detail,
	}


def todo_html(todo, on_date) -> str:
	parts = [f"<p>{escape_html(tpl.pick(_('Helpdesk to-do for {0}').format(formatdate(on_date)), 'مهام فريق الدعم ليوم ' + formatdate(on_date)))}</p>"]
	head = (_("Client"), _("Due date"), _("Status"), _("Engineer"), _("Client contact"), _("Last contact"), _("Detail"))
	for key, en, ar in SECTIONS:
		rows = todo.get(key) or []
		if not rows:
			continue
		parts.append(f"<h3 style='margin:14px 0 4px'>{escape_html(tpl.pick(_(en), ar))} ({len(rows)})</h3>")
		parts.append('<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;font-size:13px">')
		parts.append("<tr style='background:#f2f2f2'>" + "".join(f"<th align='left'>{escape_html(h)}</th>" for h in head) + "</tr>")
		for r in rows:
			link = get_url_to_form("HC Contract", r["contract"])
			parts.append(
				"<tr>"
				f"<td><a href='{link}'>{escape_html(r['client'] or '')} ({escape_html(r['contract'])})</a></td>"
				f"<td>{escape_html(formatdate(r['due_date']))}</td><td>{escape_html(_(r['status']))}</td>"
				f"<td>{escape_html(r['engineer'])}</td><td>{escape_html(r['contact'])}</td>"
				f"<td>{escape_html(r['last_contact'])}</td><td>{escape_html(r['detail'])}</td>"
				"</tr>"
			)
		parts.append("</table>")
	return tpl.wrap("".join(parts))


def send_helpdesk_todo(on_date=None, force=False) -> str:
	on_date = get_today(on_date)
	settings = get_settings()
	if not cint(settings.enable_helpdesk_todo):
		return "disabled"
	period = f"todo-{on_date}"
	todo = build_todo(on_date)
	total = sum(len(v) for v in todo.values())
	if not total:
		return "nothing to do"

	people = users_with_role(ROLE_HELPDESK)
	shared = _value_entry(settings.default_helpdesk_email)
	if shared:
		people.append(shared)
	emails = list(dict.fromkeys(p["email"] for p in people if p.get("email")))
	users = [p["user"] for p in people if p.get("user")]
	counts = ", ".join(f"{tpl.pick(_(en), ar)}: {len(todo[key])}" for key, en, ar in SECTIONS if todo[key])
	subject = tpl.pick(
		_("[HC] Helpdesk to-do {0}: {1} item(s)").format(formatdate(on_date), total),
		f"[فحص الشبكة] مهام فريق الدعم {formatdate(on_date)}: {total}",
	)
	html = todo_html(todo, on_date)
	results = []
	jobs = [(CH_EMAIL, lambda: ch.send_email(emails, [], subject, html))]
	if cint(settings.enable_popup_notifications) and users:
		jobs.append((CH_SYSTEM, lambda: ch.send_system_notification(users, subject, f"<p>{escape_html(counts)}</p>", None, "blue")))
	for channel, job in jobs:
		if not force and frappe.db.exists(
			"HC Notification Log", {"step_label": TODO_LABEL, "period_label": period, "channel": channel, "status": "Sent"}
		):
			continue
		try:
			job()
			status, error = "Sent", None
		except Exception as e:
			status, error = "Failed", str(e) if isinstance(e, ch.DeliveryError) else frappe.get_traceback()
		write_log(
			contract_name=None, flow_name=None, step_no=0, step_label=TODO_LABEL, cycle_label=period,
			channel=channel, to=emails if channel == CH_EMAIL else users, cc=[], subject=subject,
			status=status, error=error, run_date=on_date,
		)
		results.append(f"{channel}: {status}")
	return ", ".join(results) or "already sent today"


@frappe.whitelist()
def send_todo_now():
	frappe.only_for(("System Manager", "HC Technical Manager", "HC Helpdesk"))
	return _("Helpdesk to-do: {0}").format(send_helpdesk_todo(force=True))
