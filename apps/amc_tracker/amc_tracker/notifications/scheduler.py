"""Daily job (cron "0 8 * * *" in hooks.py, evaluated in the Asia/Qatar system time zone).

Run manually:
    bench --site <site> execute amc_tracker.notifications.scheduler.run_daily
Simulate another date (logs are written with that run_date):
    bench --site <site> execute amc_tracker.notifications.scheduler.run_daily --kwargs '{"on_date": "2026-12-01"}'
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, escape_html, formatdate, get_url_to_form, getdate

from amc_tracker.notifications import channels as ch
from amc_tracker.notifications.engine import (
	CH_EMAIL,
	CH_SYSTEM,
	CH_TEAMS,
	_value_entry,
	process_amc,
	users_with_role,
	write_log,
)
from amc_tracker.utils import ROLE_TECHNICAL_MANAGER, get_settings, get_today, split_list

DIGEST_LABEL = "Daily overdue digest"
RENEWAL_LABEL = "AMC renewal alert"


def run_daily(on_date=None):
	from amc_tracker.notifications.pm_todo import send_pm_todo
	from amc_tracker.notifications.summary import send_management_summary
	from amc_tracker.scheduling import is_working_day, skip_non_working_days

	on_date = get_today(on_date)
	summary = {"date": str(on_date)}
	jobs = [("management_summary", send_management_summary)]
	if skip_non_working_days() and not is_working_day(on_date):
		# Weekend / public holiday: nothing goes to the team; everything catches up on the next working day
		summary["skipped"] = "non-working day"
	else:
		jobs = [
			("notification_logs", run_notification_rules),
			("digest", send_overdue_digest),
			("renewal_alerts", send_renewal_alerts),
			("pm_todo", send_pm_todo),
			*jobs,
		]
	for key, job in jobs:
		try:
			summary[key] = job(on_date)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"AMC Tracker: {key} failed", message=frappe.get_traceback())
			summary[key] = "error (see Error Log)"
	return summary


def get_open_amcs(on_date) -> list[str]:
	"""Active AMCs with a due date that are not past their contract end."""
	rows = frappe.get_all(
		"AMC",
		filters={"status": "Active", "next_due_date": ["is", "set"]},
		fields=["name", "contract_end"],
		order_by="next_due_date asc",
	)
	return [r.name for r in rows if not r.contract_end or getdate(r.contract_end) >= on_date]


def run_notification_rules(on_date=None) -> int:
	on_date = get_today(on_date)
	written = 0
	for name in get_open_amcs(on_date):
		try:
			written += process_amc(frappe.get_doc("AMC", name), on_date)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"AMC Tracker: notification rules failed for {name}", message=frappe.get_traceback())
	return written


# ---------------------------------------------------------------------------
# Daily overdue digest
# ---------------------------------------------------------------------------


def _technical_manager_emails(settings) -> list[str]:
	emails = []
	entry = _value_entry(settings.default_technical_manager)
	if entry:
		emails.append(entry["email"])
	emails.extend(e["email"] for e in users_with_role(ROLE_TECHNICAL_MANAGER))
	return emails


def get_overdue_rows(on_date) -> list[dict]:
	open_names = set(get_open_amcs(on_date))
	rows = frappe.get_all(
		"AMC",
		filters=[["next_due_date", "is", "set"], ["next_due_date", "<", on_date]],
		fields=["name", "client_name", "amc_title", "next_due_date", "cycle_status", "cycle_label"],
		order_by="next_due_date asc",
	)
	result = []
	for row in rows:
		if row.name not in open_names:
			continue
		visits = frappe.get_all(
			"PM Visit",
			filters={"amc": row.name, "cycle_label": row.cycle_label, "status": ["!=", "Cancelled"]},
			fields=["engineer_name", "engineer", "visit_date"],
		)
		row.engineers = ", ".join(
			f"{v.engineer_name or v.engineer} ({formatdate(v.visit_date) if v.visit_date else _('no date')})" for v in visits
		)
		last = frappe.get_all(
			"AMC Notification Log",
			filters={"amc": row.name, "status": "Sent", "step_no": [">", 0]},
			fields=["step_no", "step_label", "run_date"],
			order_by="creation desc",
			limit=1,
		)
		row.days_overdue = date_diff(on_date, row.next_due_date)
		row.last_step = f"{last[0].step_no}. {last[0].step_label} ({formatdate(last[0].run_date)})" if last else "-"
		result.append(row)
	return result


def build_digest_html(rows, on_date) -> str:
	header = [_("Client / AMC"), _("PM due"), _("Days overdue"), _("Engineers (visit date)"), _("Cycle status"), _("Last notification")]
	html = [
		f"<p>{escape_html(_('Overdue preventive maintenance as of {0}').format(formatdate(on_date)))}: <b>{len(rows)}</b></p>",
		'<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px">',
		"<tr style='background:#f2f2f2'>" + "".join(f"<th align='left'>{escape_html(h)}</th>" for h in header) + "</tr>",
	]
	for row in rows:
		link = get_url_to_form("AMC", row.name)
		html.append(
			"<tr>"
			f"<td><a href='{link}'>{escape_html(row.client_name or '')} - {escape_html(row.amc_title or row.name)}</a></td>"
			f"<td>{escape_html(formatdate(row.next_due_date))}</td>"
			f"<td style='color:#c0392b'><b>{row.days_overdue}</b></td>"
			f"<td>{escape_html(row.engineers or _('Not assigned'))}</td>"
			f"<td>{escape_html(_(row.cycle_status or ''))}</td>"
			f"<td>{escape_html(row.last_step)}</td>"
			"</tr>"
		)
	html.append("</table>")
	return "".join(html)


def _already_sent(step_label, period_label, channel, amc=None) -> bool:
	filters = {"step_label": step_label, "period_label": period_label, "channel": channel, "status": "Sent"}
	if amc:
		filters["amc"] = amc
	return bool(frappe.db.exists("AMC Notification Log", filters))


def send_overdue_digest(on_date=None, force=False) -> str:
	from amc_tracker.notifications import templates as tpl

	on_date = get_today(on_date)
	settings = get_settings()
	if not cint(settings.enable_daily_digest):
		return "disabled"
	rows = get_overdue_rows(on_date)
	if not rows:
		return "no overdue AMCs"

	period_label = f"digest-{on_date}"
	recipients = list(dict.fromkeys(split_list(settings.digest_recipients) + _technical_manager_emails(settings)))
	subject = tpl.pick(
		_("[AMC] Daily overdue digest {0}: {1} overdue PM(s)").format(formatdate(on_date), len(rows)),
		f"[عقد الصيانة] ملخص الصيانة المتأخرة {formatdate(on_date)}: {len(rows)}",
	)
	html = tpl.wrap(build_digest_html(rows, on_date))
	channel_jobs = [(CH_EMAIL, lambda: ch.send_email(recipients, [], subject, html))]
	if cint(settings.enable_teams):
		facts = [
			(
				f"{r.client_name} - {r.amc_title or r.name}",
				_("Due {0} - {1} days overdue - {2} - {3}").format(
					formatdate(r.next_due_date), r.days_overdue, r.engineers or _("Not assigned"), _(r.cycle_status or "")
				),
			)
			for r in rows[:25]
		]
		text = _("{0} more not shown").format(len(rows) - 25) if len(rows) > 25 else ""
		payload = ch.build_adaptive_card(
			subject, text, facts, url=frappe.utils.get_url("/desk/amc"), url_title=_("Open AMCs"), color="Attention"
		)
		channel_jobs.append((CH_TEAMS, lambda: ch.post_to_teams(settings.default_teams_webhook_url, payload)))

	results = []
	for channel, job in channel_jobs:
		if not force and _already_sent(DIGEST_LABEL, period_label, channel):
			continue
		try:
			job()
			status, error = "Sent", None
		except Exception as e:
			status, error = "Failed", str(e) if isinstance(e, ch.DeliveryError) else frappe.get_traceback()
		write_log(
			step_label=DIGEST_LABEL, cycle_label=period_label, channel=channel,
			to=recipients if channel == CH_EMAIL else [], cc=[], subject=subject, status=status, error=error, run_date=on_date,
		)
		results.append(f"{channel}: {status}")
	return ", ".join(results) or "already sent today"


# ---------------------------------------------------------------------------
# AMC renewal alert
# ---------------------------------------------------------------------------


def send_renewal_alerts(on_date=None) -> int:
	on_date = get_today(on_date)
	settings = get_settings()
	days = cint(settings.renewal_alert_days) or 60
	amcs = frappe.get_all(
		"AMC", filters={"status": "Active", "contract_end": ["between", [on_date, add_days(on_date, days)]]}, pluck="name"
	)
	sent = 0
	for name in amcs:
		amc = frappe.get_doc("AMC", name)
		period_label = f"renewal-{amc.contract_end}"
		to = []
		entry = _value_entry(amc.account_manager)
		if entry:
			to.append(entry)
		else:
			fallback = _value_entry(settings.default_technical_manager)
			to.extend([fallback] if fallback else users_with_role(ROLE_TECHNICAL_MANAGER))

		days_left = date_diff(amc.contract_end, on_date)
		subject = _("[AMC] Renewal: {0} - {1} ends in {2} days ({3})").format(
			amc.client_name, amc.amc_title, days_left, formatdate(amc.contract_end)
		)
		url = get_url_to_form("AMC", amc.name)
		message = (
			f"<p>{escape_html(_('Hello,'))}</p>"
			f"<p>{escape_html(_('The AMC {0} for {1} ({2}) ends on {3}, in {4} days.').format(amc.amc_title, amc.client_name, amc.name, formatdate(amc.contract_end), days_left))}</p>"
			f"<p><b>{escape_html(_('Action: start the renewal discussion with the client.'))}</b></p>"
			f"<p>{escape_html(_('PM Frequency'))}: {escape_html(_(amc.frequency or ''))}<br>"
			f"{escape_html(_('Contract Start'))}: {escape_html(formatdate(amc.contract_start) if amc.contract_start else '-')}<br>"
			f"{escape_html(_('Scope'))}: {escape_html(amc.scope or '-')}</p>"
			f"<p><a href='{url}'>{escape_html(_('Open AMC'))}</a></p>"
		)
		jobs = [(CH_EMAIL, lambda to=to, s=subject, m=message, n=amc.name: ch.send_email(ch.emails_only(to), [], s, m, "AMC", n))]
		if cint(settings.enable_popup_notifications) and ch.users_only(to):
			jobs.append(
				(
					CH_SYSTEM,
					lambda to=to, s=subject, m=message, n=amc.name: ch.send_system_notification(
						ch.users_only(to), s, m, "AMC", n, "orange"
					),
				)
			)
		for channel, job in jobs:
			if _already_sent(RENEWAL_LABEL, period_label, channel, amc.name):
				continue
			try:
				job()
				status, error = "Sent", None
			except Exception as e:
				status, error = "Failed", str(e) if isinstance(e, ch.DeliveryError) else frappe.get_traceback()
			write_log(
				amc=amc.name, client_name=amc.client_name, step_label=RENEWAL_LABEL, cycle_label=period_label,
				channel=channel, to=ch.emails_only(to) if channel == CH_EMAIL else ch.users_only(to), cc=[],
				subject=subject, status=status, error=error, run_date=on_date,
			)
			sent += 1
	return sent


# ---------------------------------------------------------------------------
# Manual triggers (AMC Settings buttons)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def enqueue_daily_run():
	frappe.only_for(("System Manager", "AMC Technical Manager"))
	frappe.enqueue("amc_tracker.notifications.scheduler.run_daily", queue="long", timeout=1800)
	return _("Daily job queued. Check the Notification Log in a minute.")
