"""Data for the dashboard charts (Dashboard Chart Source "AMC Tracker Metrics")."""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, date_diff, get_first_day, getdate, today

CHARTS = {
	"PM Completed per Month": "completed",
	"PM On-time vs Late": "on_time",
	"PM Avg Days vs Due Date": "avg_days",
	"PM Due per Month": "due",
	"PM Visits per Engineer": "engineer_visits",
}


def _months(start, count):
	return [add_months(start, i) for i in range(count)]


def _label(d):
	return getdate(d).strftime("%b %y")


def _cycles():
	amcs = frappe.get_list("AMC", pluck="name", limit_page_length=0)
	if not amcs:
		return []
	return frappe.get_all(
		"PM Cycle",
		filters={"parenttype": "AMC", "parent": ["in", amcs]},
		fields=["completed_on", "due_date", "signed_off_on"],
	)


@frappe.whitelist()
def get(chart_name=None, filters=None, **kwargs):
	data = _get(CHARTS.get(chart_name, "completed"))
	# Frappe Charts draws NaN paths for an all-zero series: drop such series, and return nothing at all
	# (the chart then shows "No data yet") when no series has a value
	data["datasets"] = [d for d in data["datasets"] if any(d["values"])]
	if not data["datasets"]:
		return {"labels": [], "datasets": []}
	return data


def _get(metric):
	now = getdate(today())
	if metric == "due":
		start = get_first_day(now)
		months = _months(start, 12)
		counts = [0] * 12
		overdue = 0
		for a in frappe.get_list("AMC", filters={"status": "Active"}, fields=["next_due_date"], limit_page_length=0):
			if not a.next_due_date:
				continue
			d = getdate(a.next_due_date)
			if d < now:
				overdue += 1
				continue
			idx = (d.year - start.year) * 12 + d.month - start.month
			if 0 <= idx < 12:
				counts[idx] += 1
		return {
			"labels": [_("Overdue")] + [_label(m) for m in months],
			"datasets": [{"name": _("PM due"), "values": [overdue, *counts]}],
		}

	if metric == "engineer_visits":
		# Visits with a date in the last 90 days and the next 30 days, per engineer and status
		start, end = add_days(now, -90), add_days(now, 30)
		counts: dict[str, dict[str, int]] = {}
		for v in frappe.get_list(
			"PM Visit",
			filters={"visit_date": ["between", [start, end]], "status": ["!=", "Cancelled"]},
			fields=["engineer", "engineer_name", "status"],
			limit_page_length=0,
		):
			key = v.engineer_name or v.engineer
			bucket = "done" if v.status in ("Completed", "Report submitted") else "planned"
			counts.setdefault(key, {"done": 0, "planned": 0})[bucket] += 1
		names = sorted(counts, key=lambda k: -(counts[k]["done"] + counts[k]["planned"]))[:12]
		return {
			"labels": names,
			"datasets": [
				{"name": _("Done (last 90 days)"), "values": [counts[n]["done"] for n in names]},
				{"name": _("Planned (next 30 days)"), "values": [counts[n]["planned"] for n in names]},
			],
		}

	start = get_first_day(add_months(now, -11))
	months = _months(start, 12)
	completed, on_time, late, day_sums, day_counts = ([0] * 12 for _i in range(5))
	for cy in _cycles():
		if not cy.signed_off_on:
			continue
		d = getdate(cy.signed_off_on)
		idx = (d.year - start.year) * 12 + d.month - start.month
		if not 0 <= idx < 12:
			continue
		completed[idx] += 1
		if cy.due_date:
			diff = date_diff(cy.completed_on or d, cy.due_date)
			if diff <= 0:
				on_time[idx] += 1
			else:
				late[idx] += 1
			day_sums[idx] += diff
			day_counts[idx] += 1
	labels = [_label(m) for m in months]
	if metric == "on_time":
		return {"labels": labels, "datasets": [{"name": _("On time"), "values": on_time}, {"name": _("Late"), "values": late}]}
	if metric == "avg_days":
		values = [round(day_sums[i] / day_counts[i], 1) if day_counts[i] else 0 for i in range(12)]
		return {"labels": labels, "datasets": [{"name": _("Avg days: last visit vs due date"), "values": values}]}
	return {"labels": labels, "datasets": [{"name": _("PM cycles completed"), "values": completed}]}
