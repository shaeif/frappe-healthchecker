"""Data for the HC Tracker dashboard charts (Dashboard Chart Source "HC Tracker Metrics")."""

import frappe
from frappe import _
from frappe.utils import add_months, cint, date_diff, get_first_day, getdate, today

CHARTS = {
	"HC Completed per Month": "completed",
	"HC On-time vs Late": "on_time",
	"HC Avg Days Due to Sign-off": "avg_days",
	"HC Due per Month": "due",
}


def _months(start, count):
	return [add_months(start, i) for i in range(count)]


def _label(d):
	return getdate(d).strftime("%b %Y")


def _cycles():
	contracts = frappe.get_list("HC Contract", pluck="name", limit_page_length=0)
	if not contracts:
		return []
	return frappe.get_all(
		"HC Cycle",
		filters={"parenttype": "HC Contract", "parent": ["in", contracts]},
		fields=["hc_date", "due_date", "signed_off_on", "days_late"],
	)


@frappe.whitelist()
def get(chart_name=None, filters=None, **kwargs):
	metric = CHARTS.get(chart_name, "completed")
	now = getdate(today())
	if metric == "due":
		start = get_first_day(now)
		months = _months(start, 12)
		counts = [0] * 12
		overdue = 0
		for c in frappe.get_list(
			"HC Contract", filters={"status": ["!=", "Signed off"]}, fields=["next_due_date"], limit_page_length=0
		):
			if not c.next_due_date:
				continue
			d = getdate(c.next_due_date)
			if d < now:
				overdue += 1
				continue
			idx = (d.year - start.year) * 12 + d.month - start.month
			if 0 <= idx < 12:
				counts[idx] += 1
		return {
			"labels": [_("Overdue")] + [_label(m) for m in months],
			"datasets": [{"name": _("Health checks due"), "values": [overdue, *counts]}],
		}

	start = get_first_day(add_months(now, -11))
	months = _months(start, 12)
	completed, on_time, late, day_sums, day_counts = ([0] * 12 for _i in range(5))
	for cy in _cycles():
		done = cy.signed_off_on or cy.hc_date
		if not done:
			continue
		d = getdate(done)
		idx = (d.year - start.year) * 12 + d.month - start.month
		if not 0 <= idx < 12:
			continue
		completed[idx] += 1
		if cy.due_date:
			if cint(cy.days_late) <= 0:
				on_time[idx] += 1
			else:
				late[idx] += 1
			day_sums[idx] += date_diff(d, cy.due_date)
			day_counts[idx] += 1
	labels = [_label(m) for m in months]
	if metric == "on_time":
		return {"labels": labels, "datasets": [{"name": _("On time"), "values": on_time}, {"name": _("Late"), "values": late}]}
	if metric == "avg_days":
		values = [round(day_sums[i] / day_counts[i], 1) if day_counts[i] else 0 for i in range(12)]
		return {"labels": labels, "datasets": [{"name": _("Avg days from due date to sign-off"), "values": values}]}
	return {"labels": labels, "datasets": [{"name": _("Health checks completed"), "values": completed}]}
