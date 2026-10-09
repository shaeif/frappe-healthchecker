"""Lifecycle walkthrough and timeline preview (docs/LIFECYCLE.md).

Preview the notification timeline of one AMC (nothing is sent):
    bench --site <site> execute amc_tracker.setup.lifecycle.preview_timeline --kwargs '{"amc": "AMC-2026-0001"}'

Run the complete lifecycle on a TEST site with simulated dates (creates client LC-001 and engineer
lc.engineer@amc.test, prints every notification step by step, keeps the data so you can open it in the UI):
    bench --site <site> execute amc_tracker.setup.lifecycle.run_walkthrough
    bench --site <site> execute amc_tracker.setup.lifecycle.delete_walkthrough
"""

import frappe
from frappe.utils import add_days, formatdate, getdate, today

from amc_tracker.scheduling import shift_to_working_day

LC_CLIENT = "LC-001"
LC_ENGINEER = "lc.engineer@amc.test"
LC_ENGINEER_2 = "lc.engineer2@amc.test"


def _timeline_rows(amc_name: str, on_date=None) -> list[dict]:
	from amc_tracker.notifications.engine import evaluate_flow, get_amc_flow

	amc = frappe.get_doc("AMC", amc_name)
	flow = get_amc_flow(amc)
	if not flow:
		return []
	rows = []
	for r in evaluate_flow(amc, flow, on_date):
		ev, step = r["evaluation"], r["step"]
		rows.append(
			{
				"date": ev.planned_date,
				"step": f"{step.step_no}. {step.step_label}",
				"visit": (r["visit"].engineer_name or r["visit"].engineer) if r["visit"] else "",
				"trigger": ev.planned_label or step.trigger_mode,
				"to": ", ".join(e["email"] for e in ev.to),
				"state": ev.state,
				"reason": ev.reason,
			}
		)
	rows.sort(key=lambda x: (x["date"] is None, x["date"] or getdate("2999-01-01"), x["step"]))
	return rows


@frappe.whitelist()
def preview_timeline(amc: str, on_date: str | None = None) -> str:
	"""Plain-text timeline: every rule of the AMC's rule set with its planned date, recipients and state."""
	frappe.get_doc("AMC", amc).check_permission("read")
	lines = [f"Notification timeline for {amc} (as of {formatdate(on_date or today())}):"]
	for r in _timeline_rows(amc, on_date):
		when = formatdate(r["date"]) if r["date"] else "on event"
		visit = f" [{r['visit']}]" if r["visit"] else ""
		lines.append(f"  {when:>12}  {r['step']}{visit}  -> {r['to'] or '-'}  ({r['state']}: {r['reason']})")
	return "\n".join(lines)


# ---------------------------------------------------------------------------
# Walkthrough
# ---------------------------------------------------------------------------


def _ensure_user(email, full_name, roles=()):
	if not frappe.db.exists("User", email):
		first, _s, last = full_name.partition(" ")
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": first, "last_name": last, "send_welcome_email": 0, "user_type": "System User"}
		).insert(ignore_permissions=True)
	if roles:
		frappe.get_doc("User", email).add_roles(*roles)


def delete_walkthrough():
	for amc in frappe.get_all("AMC", filters={"client": LC_CLIENT}, pluck="name"):
		for visit in frappe.get_all("PM Visit", filters={"amc": amc}, pluck="name"):
			frappe.delete_doc("PM Visit", visit, force=True, ignore_permissions=True)
		frappe.db.delete("AMC Notification Log", {"amc": amc})
		frappe.db.delete("Client Contact Log", {"amc": amc})
		frappe.delete_doc("AMC", amc, force=True, ignore_permissions=True)
	if frappe.db.exists("Client", LC_CLIENT):
		frappe.delete_doc("Client", LC_CLIENT, force=True, ignore_permissions=True)
	for email in (LC_ENGINEER, LC_ENGINEER_2):
		frappe.db.delete("Engineer Leave", {"engineer": email})
		if frappe.db.exists("Engineer", email):
			frappe.delete_doc("Engineer", email, force=True, ignore_permissions=True)
	frappe.db.commit()
	return "deleted"


def run_walkthrough(base_date: str | None = None) -> str:
	"""Create a client, two engineers and a quarterly AMC due in 35 days, then walk through the whole cycle on
	simulated dates, printing which notifications go out at each step. For a test site only."""
	from amc_tracker.cycle import assign_engineers, sign_off
	from amc_tracker.notifications.engine import process_amc

	out = []

	def say(text=""):
		out.append(text)

	def sent_since(marker):
		rows = frappe.get_all(
			"AMC Notification Log",
			filters={"amc": amc_name, "creation": [">", marker]},
			fields=["step_no", "step_label", "channel", "status", "recipients", "cc", "pm_visit"],
			order_by="creation asc",
		)
		for r in rows:
			channel = "pop-up" if r.channel == "System Notification" else r.channel
			cc = f" cc {r.cc}" if r.cc else ""
			say(f"      -> rule {r.step_no} '{r.step_label}' by {channel} to {r.recipients}{cc} [{r.status}]")
		if not rows:
			say("      -> (nothing sent)")

	def day(d):
		return shift_to_working_day(d, 1)

	def daily(d, title):
		marker = frappe.utils.now_datetime()
		say(f"  {formatdate(d)} daily job - {title}")
		process_amc(frappe.get_doc("AMC", amc_name), d)
		frappe.db.commit()
		sent_since(marker)

	base = getdate(base_date) if base_date else getdate(today())
	delete_walkthrough()

	say("STEP 1  Admin: users and engineer profiles")
	_ensure_user(LC_ENGINEER, "Lina Engineer")
	_ensure_user(LC_ENGINEER_2, "Karim Engineer")
	for email, areas in ((LC_ENGINEER, ["Routing & Switching", "Wireless"]), (LC_ENGINEER_2, ["Security / Firewall"])):
		frappe.get_doc({"doctype": "Engineer", "user": email, "expertise": [{"expertise": a} for a in areas]}).insert(ignore_permissions=True)
		say(f"  Engineer {email}: {', '.join(areas)} -> role AMC Engineer granted: {'AMC Engineer' in frappe.get_roles(email)}")

	say("STEP 2  Client and AMC (quarterly, PM due in 35 days)")
	frappe.get_doc(
		{"doctype": "Client", "client_code": LC_CLIENT, "client_name": "Lifecycle Trading", "contact_name": "IT Manager",
			"contact_email": "it@lifecycle.amc.test", "cc_emails": "noc@lifecycle.amc.test"}
	).insert(ignore_permissions=True)
	due = day(add_days(base, 35))
	amc = frappe.get_doc(
		{"doctype": "AMC", "client": LC_CLIENT, "amc_title": "Network & Security AMC", "frequency": "Quarterly",
			"next_due_date": due, "contract_start": base, "contract_end": add_days(base, 730),
			"account_manager": "am@amc.test" if frappe.db.exists("User", "am@amc.test") else None,
			"technical_manager": "tm@amc.test" if frappe.db.exists("User", "tm@amc.test") else None,
			"engineers": [
				{"engineer": LC_ENGINEER, "expertise": "Routing & Switching"},
				{"engineer": LC_ENGINEER, "expertise": "Wireless"},
				{"engineer": LC_ENGINEER_2, "expertise": "Security / Firewall"},
			]}
	).insert(ignore_permissions=True)
	amc_name = amc.name
	frappe.db.commit()
	say(f"  {amc_name}: PM due {formatdate(due)}, cycle {amc.cycle_label}, rules '{amc.notification_flow}'")
	say("")
	say(preview_timeline(amc_name, str(base)))
	say("")

	say("STEP 3  The due date approaches")
	daily(day(base), "35 days before due")
	daily(day(add_days(due, -30)), "30 days before due: helpdesk asked to assign engineers")
	daily(day(add_days(due, -30)), "same day again: nothing is sent twice")

	say("STEP 4  Helpdesk assigns the engineers")
	marker = frappe.utils.now_datetime()
	res = assign_engineers(amc_name, [
		{"engineer": LC_ENGINEER, "expertise": ["Routing & Switching", "Wireless"]},
		{"engineer": LC_ENGINEER_2, "expertise": ["Security / Firewall"], "visit_mode": "Remote"},
	])
	frappe.db.commit()
	say(f"  {len(res['created'])} PM visits created; cycle status {frappe.db.get_value('AMC', amc_name, 'cycle_status')}")
	sent_since(marker)
	daily(day(add_days(due, -21)), "21 days before due: engineers without a date are reminded")

	say("STEP 5  Engineers set their visit dates")
	visit1 = frappe.get_doc("PM Visit", {"amc": amc_name, "engineer": LC_ENGINEER})
	visit2 = frappe.get_doc("PM Visit", {"amc": amc_name, "engineer": LC_ENGINEER_2})
	# visits on a Tuesday and Wednesday, so "2 days before" is a working day (Sunday / Monday)
	d1 = getdate(add_days(due, -12))
	while d1.weekday() != 1:
		d1 = add_days(d1, 1)
	d1 = getdate(d1)
	d2 = getdate(add_days(d1, 1))
	marker = frappe.utils.now_datetime()
	visit1.visit_date = d1
	visit1.save(ignore_permissions=True)
	say(f"  Lina sets {formatdate(d1)} (on-site)")
	visit2.visit_date = d2
	visit2.save(ignore_permissions=True)
	say(f"  Karim sets {formatdate(d2)} (remote); cycle status {frappe.db.get_value('AMC', amc_name, 'cycle_status')}")
	frappe.db.commit()
	sent_since(marker)
	marker = frappe.utils.now_datetime()
	new_d2 = getdate(add_days(d2, 1))
	visit2.reload()
	visit2.visit_date = new_d2
	visit2.reschedule_reason = "Client request"
	visit2.save(ignore_permissions=True)
	frappe.db.commit()
	say(f"  Karim moves his visit to {formatdate(new_d2)} (client request)")
	sent_since(marker)

	say("STEP 6  Before the visits")
	daily(add_days(d1, -2), "2 days before Lina's visit: preparation + client reminder")
	daily(add_days(new_d2, -2), "2 days before Karim's visit")

	say("STEP 7  Reports")
	marker = frappe.utils.now_datetime()
	visit1.reload()
	visit1.report = "/files/lifecycle-network-report.pdf"
	visit1.save(ignore_permissions=True)
	visit2.reload()
	visit2.included_in_combined = 1
	visit2.completed_on = new_d2
	visit2.save(ignore_permissions=True)
	amc = frappe.get_doc("AMC", amc_name)
	amc.combined_report = "/files/lifecycle-combined-report.pdf"
	amc.findings_summary = "No critical findings"
	amc.save(ignore_permissions=True)
	frappe.db.commit()
	say(f"  Lina attaches her report; Karim's visit is in the combined report -> cycle {frappe.db.get_value('AMC', amc_name, 'cycle_status')}")
	sent_since(marker)

	say("STEP 8  Sign-off")
	res = sign_off(amc_name)
	frappe.db.commit()
	amc.reload()
	say(f"  {res['message']} New cycle {amc.cycle_label}, status {amc.cycle_status}; PM History rows: {len(amc.cycles)}")
	say("")
	say(f"Open {amc_name} in the browser to see the visits, history, notification log and timeline.")
	say("Remove it with: bench execute amc_tracker.setup.lifecycle.delete_walkthrough")
	return "\n".join(out)
