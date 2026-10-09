"""Management summary: completed / pending / overdue health checks per client and per engineer.

Sent weekly (Sundays, previous 7 days) or monthly (1st, previous month) per HC Settings, and available
on demand as the "HC Management Summary" report and the HC Settings > Send Summary Now button.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, date_diff, escape_html, flt, formatdate, get_first_day, getdate

from hc_tracker.notifications import channels as ch
from hc_tracker.notifications import templates as tpl
from hc_tracker.notifications.engine import CH_EMAIL, CH_TEAMS, write_log
from hc_tracker.utils import get_settings, get_today, split_list

SUMMARY_LABEL = "Management summary"


def period_for(on_date, frequency: str):
	"""(from, to) covered by a summary sent on `on_date`, or None when nothing is due that day."""
	on_date = getdate(on_date)
	if frequency == "Weekly" and on_date.weekday() == 6:  # Sunday
		return add_days(on_date, -7), add_days(on_date, -1)
	if frequency == "Monthly" and on_date.day == 1:
		start = get_first_day(add_months(on_date, -1))
		return start, add_days(on_date, -1)
	return None


def build_summary(from_date, to_date, group_by: str = "Client", today=None) -> list[dict]:
	"""Rows: key, completed, on_time, late, on_time_pct, avg_days_to_signoff, pending, overdue."""
	from_date, to_date = getdate(from_date), getdate(to_date)
	today = get_today(today)
	contracts = {
		c.name: c
		for c in frappe.get_list(
			"HC Contract",
			fields=["name", "client_name", "assigned_engineer", "engineer_name", "status", "next_due_date"],
			limit_page_length=0,
		)
	}
	rows: dict[str, dict] = {}

	def row(key):
		return rows.setdefault(
			key, {"key": key, "completed": 0, "on_time": 0, "late": 0, "days": [], "pending": 0, "overdue": 0}
		)

	cycles = frappe.get_all(
		"HC Cycle",
		filters={"parenttype": "HC Contract", "parent": ["in", list(contracts) or [""]]},
		fields=["parent", "engineer", "hc_date", "due_date", "signed_off_on", "days_late"],
	)
	for cy in cycles:
		done = getdate(cy.signed_off_on or cy.hc_date) if (cy.signed_off_on or cy.hc_date) else None
		if not done or not (from_date <= done <= to_date):
			continue
		c = contracts[cy.parent]
		key = (
			f"{c.client_name} ({c.name})"
			if group_by == "Client"
			else (frappe.db.get_value("User", cy.engineer, "full_name") if cy.engineer else None) or cy.engineer or _("Unassigned")
		)
		r = row(key)
		r["completed"] += 1
		if cy.due_date:
			if cint(cy.days_late) <= 0:
				r["on_time"] += 1
			else:
				r["late"] += 1
			r["days"].append(date_diff(done, cy.due_date))

	for c in contracts.values():
		if c.status == "Signed off" or not c.next_due_date:
			continue
		key = f"{c.client_name} ({c.name})" if group_by == "Client" else (c.engineer_name or c.assigned_engineer or _("Unassigned"))
		r = row(key)
		if getdate(c.next_due_date) < today:
			r["overdue"] += 1
		else:
			r["pending"] += 1

	out = []
	for r in sorted(rows.values(), key=lambda x: (-x["overdue"], x["key"])):
		measured = r["on_time"] + r["late"]
		r["on_time_pct"] = round(r["on_time"] * 100.0 / measured, 1) if measured else None
		r["avg_days_to_signoff"] = round(sum(r["days"]) / len(r["days"]), 1) if r["days"] else None
		del r["days"]
		out.append(r)
	return out


def totals(rows) -> dict:
	t = {k: sum(r[k] for r in rows) for k in ("completed", "on_time", "late", "pending", "overdue")}
	measured = t["on_time"] + t["late"]
	t["on_time_pct"] = round(t["on_time"] * 100.0 / measured, 1) if measured else None
	return t


def summary_html(from_date, to_date) -> str:
	parts = [
		f"<p>{escape_html(tpl.pick(_('Health check summary {0} to {1}').format(formatdate(from_date), formatdate(to_date)), 'ملخص فحوصات الشبكة من ' + formatdate(from_date) + ' إلى ' + formatdate(to_date)))}</p>"
	]
	head = [_("Completed"), _("On time"), _("Late"), _("On-time %"), _("Avg days due to sign-off"), _("Pending"), _("Overdue")]
	for group, ar in (("Client", "حسب العميل"), ("Engineer", "حسب المهندس")):
		rows = build_summary(from_date, to_date, group)
		t = totals(rows)
		parts.append(f"<h3 style='margin:14px 0 4px'>{escape_html(tpl.pick(_('By {0}').format(_(group)), ar))}</h3>")
		parts.append('<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;font-size:13px">')
		parts.append(
			"<tr style='background:#f2f2f2'><th align='left'>"
			+ escape_html(_(group))
			+ "</th>"
			+ "".join(f"<th>{escape_html(h)}</th>" for h in head)
			+ "</tr>"
		)
		for r in rows + [{"key": _("Total"), **t, "avg_days_to_signoff": None}]:
			pct = "-" if r.get("on_time_pct") is None else f"{r['on_time_pct']}%"
			avg = "-" if r.get("avg_days_to_signoff") is None else r["avg_days_to_signoff"]
			color = "color:#c0392b;font-weight:bold" if r["overdue"] else ""
			parts.append(
				f"<tr><td>{escape_html(str(r['key']))}</td><td align='center'>{r['completed']}</td>"
				f"<td align='center'>{r['on_time']}</td><td align='center'>{r['late']}</td><td align='center'>{pct}</td>"
				f"<td align='center'>{avg}</td><td align='center'>{r['pending']}</td>"
				f"<td align='center' style='{color}'>{r['overdue']}</td></tr>"
			)
		parts.append("</table>")
	return tpl.wrap("".join(parts))


def recipients(settings) -> list[str]:
	from hc_tracker.notifications.engine import _value_entry, users_with_role
	from hc_tracker.utils import ROLE_TECHNICAL_MANAGER

	emails = split_list(settings.management_summary_recipients)
	entry = _value_entry(settings.default_technical_manager)
	if entry:
		emails.append(entry["email"])
	emails += [e["email"] for e in users_with_role(ROLE_TECHNICAL_MANAGER)]
	return list(dict.fromkeys(emails))


def send_management_summary(on_date=None, force=False, from_date=None, to_date=None) -> str:
	on_date = get_today(on_date)
	settings = get_settings()
	if not (from_date and to_date):
		period = period_for(on_date, settings.management_summary_frequency or "Off")
		if not period:
			return "not due today"
		from_date, to_date = period
	from_date, to_date = getdate(from_date), getdate(to_date)
	period_label = f"summary-{from_date}-{to_date}"
	to = recipients(settings)
	subject = tpl.pick(
		_("[HC] Management summary {0} to {1}").format(formatdate(from_date), formatdate(to_date)),
		f"[فحص الشبكة] الملخص الإداري {formatdate(from_date)} - {formatdate(to_date)}",
	)
	html = summary_html(from_date, to_date)
	t = totals(build_summary(from_date, to_date, "Client", on_date))
	jobs = [(CH_EMAIL, lambda: ch.send_email(to, [], subject, html))]
	if cint(settings.enable_teams):
		facts = [
			(_("Completed"), t["completed"]),
			(_("On time"), f"{t['on_time']} ({t['on_time_pct'] if t['on_time_pct'] is not None else '-'}%)"),
			(_("Late"), t["late"]),
			(_("Pending"), t["pending"]),
			(_("Overdue"), t["overdue"]),
		]
		payload = ch.build_adaptive_card(subject, "", facts, url=frappe.utils.get_url("/desk/hc-tracker"))
		jobs.append((CH_TEAMS, lambda: ch.post_to_teams(settings.default_teams_webhook_url, payload)))
	results = []
	for channel, job in jobs:
		if not force and frappe.db.exists(
			"HC Notification Log", {"step_label": SUMMARY_LABEL, "period_label": period_label, "channel": channel, "status": "Sent"}
		):
			continue
		try:
			job()
			status, error = "Sent", None
		except Exception as e:
			status, error = "Failed", str(e) if isinstance(e, ch.DeliveryError) else frappe.get_traceback()
		write_log(
			contract_name=None, flow_name=None, step_no=0, step_label=SUMMARY_LABEL, cycle_label=period_label,
			channel=channel, to=to if channel == CH_EMAIL else [], cc=[], subject=subject, status=status,
			error=error, run_date=on_date,
		)
		results.append(f"{channel}: {status}")
	return ", ".join(results) or "already sent"


@frappe.whitelist()
def send_summary_now(from_date: str | None = None, to_date: str | None = None):
	frappe.only_for(("System Manager", "HC Technical Manager"))
	to_date = getdate(to_date) if to_date else add_days(get_today(), -1)
	from_date = getdate(from_date) if from_date else add_days(to_date, -6)
	result = send_management_summary(force=True, from_date=from_date, to_date=to_date)
	return _("Management summary {0} to {1}: {2}").format(formatdate(from_date), formatdate(to_date), result)
