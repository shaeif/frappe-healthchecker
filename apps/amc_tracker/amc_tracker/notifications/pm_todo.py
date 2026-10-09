"""PM To-Do: what the helpdesk should do today (email + pop-up each working morning, and the "PM To-Do" report)."""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, escape_html, formatdate, get_datetime, get_url_to_form, getdate

from amc_tracker.notifications import channels as ch
from amc_tracker.notifications import templates as tpl
from amc_tracker.notifications.engine import CH_EMAIL, CH_SYSTEM, _value_entry, users_with_role, write_log
from amc_tracker.scheduling import next_working_days
from amc_tracker.utils import (
	CYCLE_NOT_STARTED,
	CYCLE_REPORTS,
	ROLE_HELPDESK,
	VISIT_COMPLETED,
	VISIT_SCHEDULED,
	VISIT_TO_SCHEDULE,
	get_settings,
	get_today,
)

TODO_LABEL = "Daily PM to-do"

# key, English title, Arabic title
SECTIONS = [
	("follow_up", "Follow-ups due today", "متابعات مستحقة اليوم"),
	("assign", "Assign engineers", "تعيين المهندسين"),
	("not_scheduled", "Waiting for the engineer to set the visit date", "بانتظار تحديد المهندس لموعد الزيارة"),
	("awaiting_reply", "Awaiting client reply", "بانتظار رد العميل"),
	("upcoming", "Visits in the next 2 working days (confirm with client)", "زيارات خلال يومي العمل القادمين (التأكيد مع العميل)"),
	("reports", "Visit done - report pending", "تمت الزيارة - التقرير مطلوب"),
	("signoff", "Ready for sign-off", "جاهز للاعتماد"),
	("overdue", "Overdue", "متأخر"),
]


def _open_amcs(on_date):
	rows = frappe.get_all(
		"AMC",
		filters={"status": "Active", "next_due_date": ["is", "set"]},
		fields=[
			"name", "client", "client_name", "amc_title", "next_due_date", "cycle_status", "cycle_label",
			"reminders_paused_until", "scheduling_email_sent_on", "last_contact_on", "last_contact_outcome", "contract_end",
		],
		order_by="next_due_date asc",
	)
	return {r.name: r for r in rows if not r.contract_end or getdate(r.contract_end) >= on_date}


def _contacts(client_names):
	return {
		c.name: c
		for c in frappe.get_all(
			"Client",
			filters={"name": ["in", list(client_names) or [""]]},
			fields=["name", "contact_name", "contact_phone", "contact_email"],
		)
	}


def build_todo(on_date=None) -> dict[str, list[dict]]:
	on_date = get_today(on_date)
	settings = get_settings()
	horizon = cint(settings.todo_horizon_days) or 45
	wait_days = cint(settings.client_reply_wait_days) or 3
	next_days = set(next_working_days(on_date, 2))
	todo = {key: [] for key, _en, _ar in SECTIONS}
	amcs = _open_amcs(on_date)
	contacts = _contacts({a.client for a in amcs.values()})

	visits_by_amc: dict[str, list] = {}
	for v in frappe.get_all(
		"PM Visit",
		filters={"amc": ["in", list(amcs) or [""]], "status": ["in", [VISIT_TO_SCHEDULE, VISIT_SCHEDULED, VISIT_COMPLETED]]},
		fields=["name", "amc", "cycle_label", "engineer", "engineer_name", "status", "visit_date", "visit_mode"],
		order_by="visit_date asc",
	):
		if v.cycle_label == amcs[v.amc].cycle_label:
			visits_by_amc.setdefault(v.amc, []).append(v)

	# Follow-ups from the contact log (latest log per AMC with a follow-up date <= today)
	latest = {}
	for log in frappe.get_all("Client Contact Log", fields=["amc", "name"], order_by="contact_on desc"):
		latest.setdefault(log.amc, log.name)
	followed = set()
	for log in frappe.get_all(
		"Client Contact Log",
		filters=[["follow_up_on", "is", "set"], ["follow_up_on", "<=", on_date]],
		fields=["name", "amc", "outcome", "notes", "contact_on"],
		order_by="contact_on desc",
	):
		a = amcs.get(log.amc)
		if not a or latest.get(log.amc) != log.name or a.cycle_status in (CYCLE_REPORTS,):
			continue
		todo["follow_up"].append(
			_row(a, contacts, on_date, _("{0} on {1}: {2}").format(_(log.outcome), formatdate(log.contact_on), log.notes or ""))
		)
		followed.add(a.name)

	for a in amcs.values():
		days_left = date_diff(getdate(a.next_due_date), on_date)
		paused = a.reminders_paused_until and getdate(a.reminders_paused_until) > on_date
		visits = visits_by_amc.get(a.name, [])
		unscheduled = [v for v in visits if v.status == VISIT_TO_SCHEDULE]

		if a.cycle_status == CYCLE_NOT_STARTED and 0 <= days_left <= horizon and not paused and a.name not in followed:
			todo["assign"].append(_row(a, contacts, on_date, _("PM due in {0} days").format(days_left)))
		if unscheduled and a.name not in followed:
			if a.scheduling_email_sent_on and date_diff(on_date, get_datetime(a.scheduling_email_sent_on)) >= wait_days:
				todo["awaiting_reply"].append(
					_row(a, contacts, on_date, _("Scheduling email sent on {0}").format(formatdate(a.scheduling_email_sent_on)), unscheduled[0])
				)
			elif days_left <= horizon and not paused:
				for v in unscheduled:
					todo["not_scheduled"].append(_row(a, contacts, on_date, _("PM due in {0} days").format(days_left), v))
		for v in visits:
			if v.status == VISIT_SCHEDULED and v.visit_date and getdate(v.visit_date) in next_days:
				todo["upcoming"].append(_row(a, contacts, on_date, _("{0} visit").format(_(v.visit_mode or "")), v))
			if v.visit_date and getdate(v.visit_date) < on_date and v.status in (VISIT_SCHEDULED, VISIT_COMPLETED):
				todo["reports"].append(
					_row(a, contacts, on_date, _("Visited {0} days ago").format(date_diff(on_date, v.visit_date)), v)
				)
		if a.cycle_status == CYCLE_REPORTS:
			todo["signoff"].append(_row(a, contacts, on_date, _("All visit reports submitted")))
		if days_left < 0:
			todo["overdue"].append(_row(a, contacts, on_date, _("Overdue by {0} days").format(-days_left)))
	return todo


def _row(a, contacts, on_date, detail, visit=None) -> dict:
	c = contacts.get(a.client) or frappe._dict()
	return {
		"amc": a.name,
		"client": a.client_name,
		"amc_title": a.amc_title,
		"due_date": a.next_due_date,
		"cycle_status": a.cycle_status,
		"visit": visit.name if visit else None,
		"engineer": (visit.engineer_name or visit.engineer) if visit else "",
		"visit_date": visit.visit_date if visit else None,
		"contact": " / ".join(x for x in (c.contact_name, c.contact_phone, c.contact_email) if x),
		"last_contact": f"{_(a.last_contact_outcome)} ({formatdate(a.last_contact_on)})" if a.last_contact_on else "",
		"detail": detail,
	}


def todo_html(todo, on_date) -> str:
	parts = [f"<p>{escape_html(tpl.pick(_('PM to-do for {0}').format(formatdate(on_date)), 'مهام الصيانة ليوم ' + formatdate(on_date)))}</p>"]
	head = (_("Client / AMC"), _("PM due"), _("Cycle status"), _("Engineer"), _("Visit date"), _("Client contact"), _("Detail"))
	for key, en, ar in SECTIONS:
		rows = todo.get(key) or []
		if not rows:
			continue
		parts.append(f"<h3 style='margin:14px 0 4px'>{escape_html(tpl.pick(_(en), ar))} ({len(rows)})</h3>")
		parts.append('<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;font-size:13px">')
		parts.append("<tr style='background:#f2f2f2'>" + "".join(f"<th align='left'>{escape_html(h)}</th>" for h in head) + "</tr>")
		for r in rows:
			link = get_url_to_form("PM Visit", r["visit"]) if r["visit"] else get_url_to_form("AMC", r["amc"])
			parts.append(
				"<tr>"
				f"<td><a href='{link}'>{escape_html(r['client'] or '')} - {escape_html(r['amc_title'] or r['amc'])}</a></td>"
				f"<td>{escape_html(formatdate(r['due_date']))}</td><td>{escape_html(_(r['cycle_status'] or ''))}</td>"
				f"<td>{escape_html(r['engineer'])}</td><td>{escape_html(formatdate(r['visit_date']) if r['visit_date'] else '')}</td>"
				f"<td>{escape_html(r['contact'])}</td><td>{escape_html(r['detail'])}</td>"
				"</tr>"
			)
		parts.append("</table>")
	return tpl.wrap("".join(parts))


def send_pm_todo(on_date=None, force=False) -> str:
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
	users = list(dict.fromkeys(p["user"] for p in people if p.get("user")))
	counts = ", ".join(f"{tpl.pick(_(en), ar)}: {len(todo[key])}" for key, en, ar in SECTIONS if todo[key])
	subject = tpl.pick(
		_("[AMC] PM to-do {0}: {1} item(s)").format(formatdate(on_date), total),
		f"[عقد الصيانة] مهام الصيانة {formatdate(on_date)}: {total}",
	)
	html = todo_html(todo, on_date)
	results = []
	jobs = [(CH_EMAIL, lambda: ch.send_email(emails, [], subject, html))]
	if cint(settings.enable_popup_notifications) and users:
		jobs.append((CH_SYSTEM, lambda: ch.send_system_notification(users, subject, f"<p>{escape_html(counts)}</p>")))
	for channel, job in jobs:
		if not force and frappe.db.exists(
			"AMC Notification Log", {"step_label": TODO_LABEL, "period_label": period, "channel": channel, "status": "Sent"}
		):
			continue
		try:
			job()
			status, error = "Sent", None
		except Exception as e:
			status, error = "Failed", str(e) if isinstance(e, ch.DeliveryError) else frappe.get_traceback()
		write_log(
			step_label=TODO_LABEL, cycle_label=period, channel=channel, to=emails if channel == CH_EMAIL else users,
			cc=[], subject=subject, status=status, error=error, run_date=on_date,
		)
		results.append(f"{channel}: {status}")
	return ", ".join(results) or "already sent today"


@frappe.whitelist()
def send_todo_now():
	frappe.only_for(("System Manager", "AMC Technical Manager", "AMC Helpdesk"))
	return _("PM to-do: {0}").format(send_pm_todo(force=True))
