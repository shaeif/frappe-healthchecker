"""PM cycle logic shared by AMC and PM Visit.

One AMC has one open PM cycle at a time, identified by the period label of its Next PM Due Date
(2026-10 / 2026-Q4 / 2026-H2 / 2026). For each cycle the helpdesk assigns engineers, which creates
one PM Visit per engineer. Each engineer picks the visit date (on-site or remote) and submits a report,
either on the visit or as part of a combined report attached on the AMC. When every visit has its report
the cycle is "Reports submitted"; a manager signs it off, the due date rolls forward and a new cycle starts.

The cycle status is derived from the visits (never typed in by hand):
    no visits                               -> Not started
    some visits without a date              -> Engineers assigned
    every visit has a date                  -> Scheduled
    at least one visit completed/reported   -> In progress
    every visit has its report              -> Reports submitted
"""

import json

import frappe
from frappe import _
from frappe.utils import add_months, cint, date_diff, formatdate, getdate, today

from amc_tracker.utils import (
	CYCLE_ASSIGNED,
	CYCLE_IN_PROGRESS,
	CYCLE_NOT_STARTED,
	CYCLE_REPORTS,
	CYCLE_SCHEDULED,
	CYCLE_SIGNED_OFF,
	ROLE_ENGINEER,
	VISIT_CANCELLED,
	VISIT_COMPLETED,
	VISIT_REPORTED,
	VISIT_SCHEDULED,
	VISIT_TO_SCHEDULE,
	can_assign,
	can_sign_off,
	full_name,
	get_interval_months,
	get_period_label,
)


def cycle_label_of(amc) -> str:
	return get_period_label(amc.next_due_date, amc.frequency)


def get_cycle_visits(amc_name: str, cycle_label: str, include_cancelled: bool = False) -> list:
	filters = {"amc": amc_name, "cycle_label": cycle_label}
	if not include_cancelled:
		filters["status"] = ["!=", VISIT_CANCELLED]
	return frappe.get_all(
		"PM Visit",
		filters=filters,
		fields=[
			"name", "engineer", "engineer_name", "status", "visit_date", "visit_mode", "report",
			"included_in_combined", "completed_on", "start_time", "end_time",
		],
		order_by="visit_date asc, creation asc",
	)


def compute_cycle_status(visits: list) -> str:
	if not visits:
		return CYCLE_NOT_STARTED
	statuses = [v.status for v in visits]
	if all(s == VISIT_REPORTED for s in statuses):
		return CYCLE_REPORTS
	if any(s in (VISIT_COMPLETED, VISIT_REPORTED) for s in statuses):
		return CYCLE_IN_PROGRESS
	if all(v.visit_date for v in visits):
		return CYCLE_SCHEDULED
	return CYCLE_ASSIGNED


def visit_status(visit, amc_combined_report: str | None) -> str:
	"""Status of a PM Visit from its data (Cancelled is kept as set)."""
	if visit.status == VISIT_CANCELLED:
		return VISIT_CANCELLED
	if visit.report or (cint(visit.included_in_combined) and amc_combined_report):
		return VISIT_REPORTED
	if visit.completed_on:
		return VISIT_COMPLETED
	if visit.visit_date:
		return VISIT_SCHEDULED
	return VISIT_TO_SCHEDULE


def refresh_cycle_status(amc_name: str, fire: bool = True) -> str:
	"""Recompute the AMC's cycle status from its visits; fire 'On cycle status change' rules when it changes."""
	amc = frappe.get_doc("AMC", amc_name)
	label = cycle_label_of(amc)
	new_status = compute_cycle_status(get_cycle_visits(amc.name, label))
	if new_status == amc.cycle_status and amc.cycle_label == label:
		return new_status
	amc.db_set({"cycle_status": new_status, "cycle_label": label}, update_modified=False)
	if fire and new_status != CYCLE_NOT_STARTED and not (frappe.flags.in_import or frappe.flags.in_install):
		from amc_tracker.notifications.engine import fire_status_change

		try:
			fire_status_change(amc, new_status, label)
		except Exception:
			frappe.log_error(title=f"AMC Tracker: status notification failed for {amc.name}")
	return new_status


# ---------------------------------------------------------------------------
# Assign engineers (helpdesk)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def assign_engineers(amc: str, rows) -> dict:
	"""Create one PM Visit per engineer for the AMC's current cycle.

	rows: [{"engineer": user, "expertise": [names], "visit_mode": "On-site"|"Remote"}]
	Engineers not yet on the AMC are added to its Engineers table. Engineers who already have an open
	visit in this cycle are skipped (add a second visit from the PM Visit form if really needed).
	"""
	if not can_assign():
		frappe.throw(_("Only the helpdesk or a Technical Manager can assign engineers."), frappe.PermissionError)
	rows = json.loads(rows) if isinstance(rows, str) else (rows or [])
	doc = frappe.get_doc("AMC", amc)
	doc.check_permission("write")
	if doc.status != "Active":
		frappe.throw(_("The AMC is {0}. Assign engineers only on active AMCs.").format(_(doc.status)))
	label = cycle_label_of(doc)
	existing = {v.engineer for v in get_cycle_visits(doc.name, label)}

	team = {(r.engineer, r.expertise or "") for r in doc.engineers}
	team_changed = False
	created, skipped = [], []
	merged: dict[str, dict] = {}
	for row in rows:
		engineer = (row.get("engineer") or "").strip()
		if not engineer:
			continue
		entry = merged.setdefault(engineer, {"expertise": [], "visit_mode": row.get("visit_mode") or "On-site"})
		for exp in row.get("expertise") or []:
			if exp and exp not in entry["expertise"]:
				entry["expertise"].append(exp)
	if not merged:
		frappe.throw(_("Select at least one engineer."))

	for engineer, entry in merged.items():
		if ROLE_ENGINEER not in frappe.get_roles(engineer):
			frappe.throw(_("{0} does not have the role {1}.").format(full_name(engineer), ROLE_ENGINEER))
		for exp in entry["expertise"] or [""]:
			on_team = (engineer, exp) in team or (not exp and any(t[0] == engineer for t in team))
			if not on_team:
				doc.append("engineers", {"engineer": engineer, "expertise": exp or None})
				team.add((engineer, exp))
				team_changed = True
	if team_changed:
		doc.save()

	for engineer, entry in merged.items():
		if engineer in existing:
			skipped.append(full_name(engineer))
			continue
		visit = frappe.new_doc("PM Visit")
		visit.update(
			{
				"amc": doc.name,
				"engineer": engineer,
				"visit_mode": entry["visit_mode"],
				"cycle_label": label,
				"due_date": doc.next_due_date,
			}
		)
		for exp in entry["expertise"]:
			visit.append("expertise_covered", {"expertise": exp})
		visit.flags.engineer_on_team = True
		visit.insert()
		created.append(visit.name)

	refresh_cycle_status(doc.name)
	return {"created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# Sign-off (Account / Technical Manager)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def sign_off(amc: str) -> dict:
	"""Close the current cycle: history row, last PM date, roll the due date, start the next cycle."""
	if not can_sign_off():
		frappe.throw(
			_("Only an AMC Account Manager or AMC Technical Manager can sign off a PM cycle."), frappe.PermissionError
		)
	doc = frappe.get_doc("AMC", amc)
	doc.check_permission("write")
	label = cycle_label_of(doc)
	visits = get_cycle_visits(doc.name, label)
	if not visits:
		frappe.throw(_("No PM visits in cycle {0}. Assign engineers first.").format(label))
	pending = [v for v in visits if v.status != VISIT_REPORTED]
	if pending:
		frappe.throw(
			_("Reports are missing for: {0}").format(
				", ".join(f"{v.engineer_name or v.engineer} ({_(v.status)})" for v in pending)
			),
			title=_("Not ready for sign-off"),
		)

	previous_due = getdate(doc.next_due_date)
	dates = [getdate(v.visit_date) for v in visits if v.visit_date] + [getdate(v.completed_on) for v in visits if v.completed_on]
	last_visit = max(dates) if dates else getdate(today())
	engineers = list(dict.fromkeys(v.engineer_name or v.engineer for v in visits))
	doc.append(
		"cycles",
		{
			"period_label": label,
			"due_date": previous_due,
			"completed_on": last_visit,
			"signed_off_on": getdate(today()),
			"days_late": date_diff(last_visit, previous_due),
			"engineers": ", ".join(engineers),
			"visits": ", ".join(v.name for v in visits),
			"combined_report": doc.combined_report,
			"client_signoff": doc.client_signoff,
			"findings_summary": doc.findings_summary,
			"signed_off_by": frappe.session.user,
		},
	)
	doc.last_pm_date = last_visit
	# Roll forward from the PREVIOUS DUE DATE, not from the sign-off date
	doc.next_due_date = add_months(previous_due, doc.interval_months or get_interval_months(doc.frequency))
	doc.combined_report = None
	doc.client_signoff = None
	doc.findings_summary = None
	doc.cycle_status = CYCLE_NOT_STARTED
	doc.flags.signed_off_cycle = label
	doc.save()

	from amc_tracker.notifications.engine import fire_status_change

	try:
		fire_status_change(doc, CYCLE_SIGNED_OFF, label)
	except Exception:
		frappe.log_error(title=f"AMC Tracker: sign-off notification failed for {doc.name}")
	return {
		"cycle": label,
		"next_due_date": str(doc.next_due_date),
		"message": _("Cycle {0} signed off. Next PM due on {1}.").format(label, formatdate(doc.next_due_date)),
	}


@frappe.whitelist()
def get_cycle_overview(amc: str) -> dict:
	"""Data for the 'PM Visits (current cycle)' panel on the AMC form."""
	doc = frappe.get_doc("AMC", amc)
	doc.check_permission("read")
	label = cycle_label_of(doc)
	visits = get_cycle_visits(doc.name, label, include_cancelled=True)
	expertise = {}
	for row in frappe.get_all(
		"PM Visit Expertise",
		filters={"parenttype": "PM Visit", "parent": ["in", [v.name for v in visits] or [""]]},
		fields=["parent", "expertise"],
	):
		expertise.setdefault(row.parent, []).append(row.expertise)
	return {
		"cycle_label": label,
		"cycle_status": doc.cycle_status,
		"due_date": str(doc.next_due_date) if doc.next_due_date else None,
		"can_assign": can_assign() and frappe.has_permission("AMC", "write", doc),
		"can_sign_off": can_sign_off() and doc.cycle_status == CYCLE_REPORTS,
		"combined_report": doc.combined_report,
		"visits": [
			{
				**v,
				"visit_date": str(v.visit_date) if v.visit_date else None,
				"completed_on": str(v.completed_on) if v.completed_on else None,
				"start_time": str(v.start_time) if v.start_time else None,
				"end_time": str(v.end_time) if v.end_time else None,
				"expertise": expertise.get(v.name, []),
			}
			for v in visits
		],
	}
