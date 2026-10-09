"""Daily job (cron "0 8 * * *" in hooks.py, evaluated in the Asia/Qatar system time zone).

Run manually:
    bench --site <site> execute hc_tracker.notifications.scheduler.run_daily
Simulate another date (logs are written with that run_date):
    bench --site <site> execute hc_tracker.notifications.scheduler.run_daily --kwargs '{"on_date": "2026-12-01"}'
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, escape_html, formatdate, get_url_to_form, getdate

from hc_tracker.notifications import channels as ch
from hc_tracker.notifications.engine import (
	CH_EMAIL,
	CH_SYSTEM,
	CH_TEAMS,
	_value_entry,
	process_contract,
	users_with_role,
	write_log,
)
from hc_tracker.utils import ROLE_TECHNICAL_MANAGER, get_settings, get_today, split_list

DIGEST_LABEL = "Daily overdue digest"
RENEWAL_LABEL = "Contract renewal alert"


def run_daily(on_date=None):
	on_date = get_today(on_date)
	summary = {"date": str(on_date)}
	for key, job in (
		("flow_logs", run_notification_flows),
		("digest", send_overdue_digest),
		("renewal_alerts", send_renewal_alerts),
	):
		try:
			summary[key] = job(on_date)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"HC Tracker: {key} failed", message=frappe.get_traceback())
			summary[key] = "error (see Error Log)"
	return summary


def get_open_contracts(on_date) -> list[str]:
	"""Contracts with a due date, not signed off, and not past their contract end."""
	rows = frappe.get_all(
		"HC Contract",
		filters={"status": ["!=", "Signed off"], "next_due_date": ["is", "set"]},
		fields=["name", "contract_end"],
		order_by="next_due_date asc",
	)
	return [r.name for r in rows if not r.contract_end or getdate(r.contract_end) >= on_date]


def run_notification_flows(on_date=None) -> int:
	on_date = get_today(on_date)
	written = 0
	for name in get_open_contracts(on_date):
		try:
			contract = frappe.get_doc("HC Contract", name)
			written += process_contract(contract, on_date)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"HC Tracker: notification flow failed for {name}", message=frappe.get_traceback())
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
	open_names = set(get_open_contracts(on_date))
	rows = frappe.get_all(
		"HC Contract",
		filters={"next_due_date": ["<", on_date], "status": ["!=", "Signed off"]},
		fields=[
			"name",
			"client_name",
			"next_due_date",
			"assigned_engineer",
			"engineer_name",
			"status",
		],
		order_by="next_due_date asc",
	)
	result = []
	for row in rows:
		if row.name not in open_names:
			continue
		last = frappe.get_all(
			"HC Notification Log",
			filters={"contract": row.name, "status": "Sent", "step_no": [">", 0]},
			fields=["step_no", "step_label", "run_date"],
			order_by="creation desc",
			limit=1,
		)
		row.days_overdue = date_diff(on_date, row.next_due_date)
		row.last_step = (
			f"{last[0].step_no}. {last[0].step_label} ({formatdate(last[0].run_date)})" if last else "-"
		)
		result.append(row)
	return result


def build_digest_html(rows, on_date) -> str:
	header = [_("Client"), _("Due date"), _("Days overdue"), _("Engineer"), _("Status"), _("Last step sent")]
	html = [
		f"<p>{escape_html(_('Overdue health checks as of {0}').format(formatdate(on_date)))}: <b>{len(rows)}</b></p>",
		'<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px">',
		"<tr style='background:#f2f2f2'>" + "".join(f"<th align='left'>{escape_html(h)}</th>" for h in header) + "</tr>",
	]
	for row in rows:
		link = get_url_to_form("HC Contract", row.name)
		html.append(
			"<tr>"
			f"<td><a href='{link}'>{escape_html(row.client_name or '')} ({escape_html(row.name)})</a></td>"
			f"<td>{escape_html(formatdate(row.next_due_date))}</td>"
			f"<td style='color:#c0392b'><b>{row.days_overdue}</b></td>"
			f"<td>{escape_html(row.engineer_name or row.assigned_engineer or '-')}</td>"
			f"<td>{escape_html(row.status or '')}</td>"
			f"<td>{escape_html(row.last_step)}</td>"
			"</tr>"
		)
	html.append("</table>")
	return "".join(html)


def _already_sent(step_label, period_label, channel, contract=None) -> bool:
	filters = {"step_label": step_label, "period_label": period_label, "channel": channel, "status": "Sent"}
	if contract:
		filters["contract"] = contract
	return bool(frappe.db.exists("HC Notification Log", filters))


def send_overdue_digest(on_date=None, force=False) -> str:
	on_date = get_today(on_date)
	settings = get_settings()
	if not cint(settings.enable_daily_digest):
		return "disabled"

	rows = get_overdue_rows(on_date)
	if not rows:
		return "no overdue contracts"

	period_label = f"digest-{on_date}"
	recipients = list(dict.fromkeys(split_list(settings.digest_recipients) + _technical_manager_emails(settings)))
	subject = _("[HC] Daily overdue digest {0}: {1} overdue health check(s)").format(formatdate(on_date), len(rows))
	html = build_digest_html(rows, on_date)
	results = []

	channel_jobs = [(CH_EMAIL, lambda: ch.send_email(recipients, [], subject, html))]
	if cint(settings.enable_teams):
		facts = [
			(
				f"{r.client_name} ({r.name})",
				_("Due {0} - {1} days overdue - {2} - {3}").format(
					formatdate(r.next_due_date), r.days_overdue, r.engineer_name or r.assigned_engineer or "-", r.status
				),
			)
			for r in rows[:25]
		]
		text = _("{0} more not shown").format(len(rows) - 25) if len(rows) > 25 else ""
		payload = ch.build_adaptive_card(
			subject,
			text,
			facts,
			url=frappe.utils.get_url("/desk/hc-contract"),
			url_title=_("Open HC contracts"),
			color="Attention",
		)
		channel_jobs.append((CH_TEAMS, lambda: ch.post_to_teams(settings.default_teams_webhook_url, payload)))

	for channel, job in channel_jobs:
		if not force and _already_sent(DIGEST_LABEL, period_label, channel):
			continue
		try:
			job()
			status, error = "Sent", None
		except Exception as e:
			status, error = "Failed", str(e) if isinstance(e, ch.DeliveryError) else frappe.get_traceback()
		write_log(
			contract_name=None,
			flow_name=None,
			step_no=0,
			step_label=DIGEST_LABEL,
			cycle_label=period_label,
			channel=channel,
			to=recipients if channel == CH_EMAIL else [],
			cc=[],
			subject=subject,
			status=status,
			error=error,
			run_date=on_date,
		)
		results.append(f"{channel}: {status}")
	return ", ".join(results) or "already sent today"


# ---------------------------------------------------------------------------
# Contract renewal alert
# ---------------------------------------------------------------------------


def send_renewal_alerts(on_date=None) -> int:
	on_date = get_today(on_date)
	settings = get_settings()
	days = cint(settings.renewal_alert_days) or 60
	contracts = frappe.get_all(
		"HC Contract",
		filters={"contract_end": ["between", [on_date, add_days(on_date, days)]]},
		fields=["name"],
	)
	sent = 0
	for row in contracts:
		contract = frappe.get_doc("HC Contract", row.name)
		period_label = f"renewal-{contract.contract_end}"

		to = []
		entry = _value_entry(contract.account_manager)
		if entry:
			to.append(entry)
		else:
			fallback = _value_entry(settings.default_technical_manager)
			to.extend([fallback] if fallback else users_with_role(ROLE_TECHNICAL_MANAGER))

		days_left = date_diff(contract.contract_end, on_date)
		subject = _("[HC] Contract renewal: {0} ends in {1} days ({2})").format(
			contract.client_name, days_left, formatdate(contract.contract_end)
		)
		url = get_url_to_form("HC Contract", contract.name)
		message = (
			f"<p>{escape_html(_('Hello,'))}</p>"
			f"<p>{escape_html(_('The health check contract for {0} ({1}) ends on {2}, in {3} days.').format(contract.client_name, contract.name, formatdate(contract.contract_end), days_left))}</p>"
			f"<p><b>{escape_html(_('Action: start the renewal discussion with the client.'))}</b></p>"
			f"<p>{escape_html(_('Frequency'))}: {escape_html(contract.frequency or '')}<br>"
			f"{escape_html(_('Contract start'))}: {escape_html(formatdate(contract.contract_start) if contract.contract_start else '-')}<br>"
			f"{escape_html(_('Scope'))}: {escape_html(contract.scope or '-')}</p>"
			f"<p><a href='{url}'>{escape_html(_('Open contract'))}</a></p>"
		)

		jobs = [(CH_EMAIL, lambda to=to, subject=subject, message=message: ch.send_email(ch.emails_only(to), [], subject, message, contract.name))]
		if cint(settings.enable_popup_notifications) and ch.users_only(to):
			jobs.append(
				(
					CH_SYSTEM,
					lambda to=to, subject=subject, message=message, name=contract.name: ch.send_system_notification(
						ch.users_only(to), subject, message, name, "orange"
					),
				)
			)

		for channel, job in jobs:
			if _already_sent(RENEWAL_LABEL, period_label, channel, contract.name):
				continue
			try:
				job()
				status, error = "Sent", None
			except Exception as e:
				status, error = "Failed", str(e) if isinstance(e, ch.DeliveryError) else frappe.get_traceback()
			write_log(
				contract_name=contract.name,
				flow_name=None,
				step_no=0,
				step_label=RENEWAL_LABEL,
				cycle_label=period_label,
				channel=channel,
				to=ch.emails_only(to) if channel == CH_EMAIL else ch.users_only(to),
				cc=[],
				subject=subject,
				status=status,
				error=error,
				run_date=on_date,
			)
			sent += 1
	return sent


# ---------------------------------------------------------------------------
# Manual triggers (HC Settings buttons)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def enqueue_daily_run():
	frappe.only_for(("System Manager", "HC Technical Manager"))
	frappe.enqueue("hc_tracker.notifications.scheduler.run_daily", queue="long", timeout=1800)
	return _("Daily HC job queued. Check HC Notification Log in a minute.")
