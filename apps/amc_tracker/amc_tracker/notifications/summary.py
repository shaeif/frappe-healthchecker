"""Management summary: completed / pending / overdue preventive maintenance per client and per engineer.

Sent weekly (Sundays, previous 7 days) or monthly (1st, previous month) per AMC Settings, and available
on demand as the "AMC Management Summary" report and the AMC Settings > Send Management Summary Now button.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, date_diff, escape_html, formatdate, get_first_day, getdate

from amc_tracker.notifications import channels as ch
from amc_tracker.notifications import templates as tpl
from amc_tracker.notifications.engine import CH_EMAIL, CH_TEAMS, write_log
from amc_tracker.utils import get_settings, get_today, split_list

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
	"""Rows: key, completed, on_time, late, on_time_pct, avg_days_to_signoff, pending, overdue.

	By Client: PM cycles signed off in the period (one per AMC cycle).
	By Engineer: PM visits whose report was submitted in the period (one per engineer visit).
	"""
	from_date, to_date = getdate(from_date), getdate(to_date)
	today = get_today(today)
	amcs = {
		a.name: a
		for a in frappe.get_list(
			"AMC",
			fields=["name", "client_name", "amc_title", "status", "next_due_date", "cycle_label"],
			limit_page_length=0,
		)
	}
	rows: dict[str, dict] = {}

	def row(key):
		return rows.setdefault(
			key, {"key": key, "completed": 0, "on_time": 0, "late": 0, "days": [], "pending": 0, "overdue": 0}
		)

	def count(r, done, due):
		r["completed"] += 1
		if due:
			if date_diff(done, due) <= 0:
				r["on_time"] += 1
			else:
				r["late"] += 1
			r["days"].append(date_diff(done, due))

	def amc_key(a):
		return f"{a.client_name} - {a.amc_title or a.name}"

	if group_by == "Client":
		for cy in frappe.get_all(
			"PM Cycle",
			filters={"parenttype": "AMC", "parent": ["in", list(amcs) or [""]]},
			fields=["parent", "completed_on", "due_date", "signed_off_on"],
		):
			done = getdate(cy.signed_off_on) if cy.signed_off_on else None
			if not done or not (from_date <= done <= to_date):
				continue
			count(row(amc_key(amcs[cy.parent])), getdate(cy.completed_on or done), cy.due_date)
		for a in amcs.values():
			if a.status != "Active" or not a.next_due_date:
				continue
			r = row(amc_key(a))
			if getdate(a.next_due_date) < today:
				r["overdue"] += 1
			else:
				r["pending"] += 1
	else:
		for v in frappe.get_all(
			"PM Visit",
			filters={"amc": ["in", list(amcs) or [""]], "status": ["!=", "Cancelled"]},
			fields=["amc", "engineer", "engineer_name", "status", "visit_date", "completed_on", "due_date", "cycle_label"],
		):
			key = v.engineer_name or v.engineer or _("Unassigned")
			if v.status == "Report submitted":
				done = getdate(v.completed_on or v.visit_date) if (v.completed_on or v.visit_date) else None
				if done and from_date <= done <= to_date:
					count(row(key), done, v.due_date)
				continue
			a = amcs.get(v.amc)
			if not a or a.status != "Active" or v.cycle_label != a.cycle_label:
				continue
			r = row(key)
			if a.next_due_date and getdate(a.next_due_date) < today:
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
		f"<p>{escape_html(tpl.pick(_('Preventive maintenance summary {0} to {1}').format(formatdate(from_date), formatdate(to_date)), 'ملخص الصيانة الوقائية من ' + formatdate(from_date) + ' إلى ' + formatdate(to_date)))}</p>"
	]
	head = [_("Completed"), _("On time"), _("Late"), _("On-time %"), _("Avg days vs due date"), _("Pending"), _("Overdue")]
	for group, ar in (("Client", "حسب العميل والعقد"), ("Engineer", "حسب المهندس (زيارات)")):
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
	from amc_tracker.notifications.engine import _value_entry, users_with_role
	from amc_tracker.utils import ROLE_TECHNICAL_MANAGER

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
		_("[AMC] Management summary {0} to {1}").format(formatdate(from_date), formatdate(to_date)),
		f"[عقد الصيانة] الملخص الإداري {formatdate(from_date)} - {formatdate(to_date)}",
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
		payload = ch.build_adaptive_card(subject, "", facts, url=frappe.utils.get_url("/desk/amc-tracker"))
		jobs.append((CH_TEAMS, lambda: ch.post_to_teams(settings.default_teams_webhook_url, payload)))
	results = []
	for channel, job in jobs:
		if not force and frappe.db.exists(
			"AMC Notification Log", {"step_label": SUMMARY_LABEL, "period_label": period_label, "channel": channel, "status": "Sent"}
		):
			continue
		try:
			job()
			status, error = "Sent", None
		except Exception as e:
			status, error = "Failed", str(e) if isinstance(e, ch.DeliveryError) else frappe.get_traceback()
		write_log(
			step_label=SUMMARY_LABEL, cycle_label=period_label,
			channel=channel, to=to if channel == CH_EMAIL else [], cc=[], subject=subject, status=status,
			error=error, run_date=on_date,
		)
		results.append(f"{channel}: {status}")
	return ", ".join(results) or "already sent"


@frappe.whitelist()
def send_summary_now(from_date: str | None = None, to_date: str | None = None):
	frappe.only_for(("System Manager", "AMC Admin", "AMC Technical Manager"))
	to_date = getdate(to_date) if to_date else add_days(get_today(), -1)
	from_date = getdate(from_date) if from_date else add_days(to_date, -6)
	result = send_management_summary(force=True, from_date=from_date, to_date=to_date)
	return _("Management summary {0} to {1}: {2}").format(formatdate(from_date), formatdate(to_date), result)
