"""Default "Standard HC Escalation" notification flows.

One default flow (applies to All, Quarterly day values) plus one copy per frequency whose day
values match that frequency. Contracts automatically use the flow matching their frequency.
Everything here is editable afterwards in the UI (HC Notification Flow).
"""

import frappe

from hc_tracker.notifications import templates as tpl

# frequency: (first_reminder days before due -> Helpdesk, second_reminder days before due -> TM)
FREQUENCY_DAYS = {
	"Monthly": (7, 3),
	"Quarterly": (30, 7),
	"Half-yearly": (45, 14),
	"Yearly": (60, 30),
}
# days before the booked date the client receives the visit reminder
CLIENT_REMINDER_DAYS = {"Monthly": 1, "Quarterly": 2, "Half-yearly": 2, "Yearly": 2}

# Arabic templates per default step label (filled on new flows and by the v1.3 patch)
ARABIC_TEMPLATES = {
	"Helpdesk": (tpl.HELPDESK_SUBJECT_AR, tpl.HELPDESK_MESSAGE_AR),
	"Assigned Engineer - HC booked": (tpl.ENGINEER_BOOKED_SUBJECT_AR, tpl.ENGINEER_BOOKED_MESSAGE_AR),
	"Assigned Engineer - prep reminder": (tpl.ENGINEER_PREP_SUBJECT_AR, tpl.ENGINEER_PREP_MESSAGE_AR),
	"Technical Manager": (tpl.TM_SUBJECT_AR, tpl.TM_MESSAGE_AR),
	"Overdue escalation": (tpl.OVERDUE_SUBJECT_AR, tpl.OVERDUE_MESSAGE_AR),
	"Report sent - Account Manager": (tpl.REPORT_SENT_SUBJECT_AR, tpl.REPORT_SENT_MESSAGE_AR),
	"Helpdesk follow-up (not booked)": (tpl.HELPDESK_FOLLOWUP_SUBJECT_AR, tpl.HELPDESK_FOLLOWUP_MESSAGE_AR),
	"Assigned Engineer - HC rescheduled": (tpl.RESCHEDULED_SUBJECT_AR, tpl.RESCHEDULED_MESSAGE_AR),
	"Client - visit reminder": (tpl.CLIENT_REMINDER_SUBJECT_AR, tpl.CLIENT_REMINDER_MESSAGE_AR),
}

DEFAULT_FLOW_NAME = "Standard HC Escalation"

FLOW_DEFINITIONS = [
	# (flow_name, applies_to_frequency, is_default, day values taken from)
	(DEFAULT_FLOW_NAME, "All", 1, "Quarterly"),
	(f"{DEFAULT_FLOW_NAME} - Monthly", "Monthly", 0, "Monthly"),
	(f"{DEFAULT_FLOW_NAME} - Quarterly", "Quarterly", 0, "Quarterly"),
	(f"{DEFAULT_FLOW_NAME} - Half-yearly", "Half-yearly", 0, "Half-yearly"),
	(f"{DEFAULT_FLOW_NAME} - Yearly", "Yearly", 0, "Yearly"),
]

OPEN_LATER_STATUSES = "Scheduled,In progress,Report sent,Signed off"


def v13_steps(client_reminder_days: int = 2) -> list[dict]:
	"""Steps added in v1.3 (also appended to existing default flows by the upgrade patch)."""
	return [
		{
			"step_no": 8,
			"step_label": "Assigned Engineer - HC rescheduled",
			"enabled": 1,
			"recipient_type": "Contract Field",
			"recipient_field": "assigned_engineer",
			"cc_type": "Role",
			"cc_role": "HC Helpdesk",
			"trigger_mode": "On reschedule",
			"channel": "Email",
			"show_popup": 1,
			"repeat_every_days": 0,
			"subject_template": tpl.RESCHEDULED_SUBJECT,
			"message_template": tpl.RESCHEDULED_MESSAGE,
		},
		{
			"step_no": 9,
			"step_label": "Client - visit reminder",
			"enabled": 1,
			"recipient_type": "Client Contact",
			"cc_type": "Role",
			"cc_role": "HC Helpdesk",
			"trigger_mode": "Days before scheduled date",
			"trigger_days": client_reminder_days,
			"only_if_status_in": "Scheduled",
			"channel": "Email",
			"show_popup": 0,
			"repeat_every_days": 0,
			"subject_template": tpl.CLIENT_REMINDER_SUBJECT,
			"message_template": tpl.CLIENT_REMINDER_MESSAGE,
		},
	]


def add_arabic(step: dict) -> dict:
	if step["step_label"] in ARABIC_TEMPLATES:
		step.setdefault("subject_template_ar", ARABIC_TEMPLATES[step["step_label"]][0])
		step.setdefault("message_template_ar", ARABIC_TEMPLATES[step["step_label"]][1])
	return step


def build_steps(first_reminder: int, second_reminder: int, client_reminder_days: int = 2) -> list[dict]:
	return [add_arabic(step) for step in _base_steps(first_reminder, second_reminder) + v13_steps(client_reminder_days)]


def _base_steps(first_reminder: int, second_reminder: int) -> list[dict]:
	return [
		{
			"step_no": 1,
			"step_label": "Helpdesk",
			"enabled": 1,
			"recipient_type": "Role",
			"recipient_role": "HC Helpdesk",
			"trigger_mode": "Days before due date",
			"trigger_days": first_reminder,
			"only_if_status_in": "Not started",
			"stop_when_status": OPEN_LATER_STATUSES,
			"channel": "Email",
			"show_popup": 1,
			"repeat_every_days": 0,
			"subject_template": tpl.HELPDESK_SUBJECT,
			"message_template": tpl.HELPDESK_MESSAGE,
		},
		{
			"step_no": 2,
			"step_label": "Assigned Engineer - HC booked",
			"enabled": 1,
			"recipient_type": "Contract Field",
			"recipient_field": "assigned_engineer",
			"cc_type": "Role",
			"cc_role": "HC Helpdesk",
			"trigger_mode": "On status change",
			"on_status": "Scheduled",
			"channel": "Email",
			"show_popup": 1,
			"repeat_every_days": 0,
			"subject_template": tpl.ENGINEER_BOOKED_SUBJECT,
			"message_template": tpl.ENGINEER_BOOKED_MESSAGE,
		},
		{
			"step_no": 3,
			"step_label": "Assigned Engineer - prep reminder",
			"enabled": 1,
			"recipient_type": "Contract Field",
			"recipient_field": "assigned_engineer",
			"cc_type": "Role",
			"cc_role": "HC Helpdesk",
			"trigger_mode": "Days before scheduled date",
			"trigger_days": 3,
			"only_if_status_in": "Scheduled",
			"channel": "Email",
			"show_popup": 1,
			"repeat_every_days": 0,
			"subject_template": tpl.ENGINEER_PREP_SUBJECT,
			"message_template": tpl.ENGINEER_PREP_MESSAGE,
		},
		{
			"step_no": 4,
			"step_label": "Technical Manager",
			"enabled": 1,
			"recipient_type": "Contract Field",
			"recipient_field": "technical_manager",
			"fallback_role": "HC Technical Manager",
			"trigger_mode": "Days before due date",
			"trigger_days": second_reminder,
			"only_if_status_in": "Not started",
			"channel": "Email + Teams",
			"show_popup": 1,
			"repeat_every_days": 0,
			"subject_template": tpl.TM_SUBJECT,
			"message_template": tpl.TM_MESSAGE,
		},
		{
			"step_no": 5,
			"step_label": "Overdue escalation",
			"enabled": 1,
			"recipient_type": "Contract Field",
			"recipient_field": "technical_manager",
			"fallback_role": "HC Technical Manager",
			"cc_type": "Contract Field",
			"cc_field": "account_manager",
			"trigger_mode": "Days after due date (overdue)",
			"trigger_days": 1,
			"stop_when_status": "Signed off",
			"ignore_pause": 1,
			"channel": "Email + Teams",
			"show_popup": 1,
			"repeat_every_days": 1,
			"subject_template": tpl.OVERDUE_SUBJECT,
			"message_template": tpl.OVERDUE_MESSAGE,
		},
		{
			"step_no": 6,
			"step_label": "Report sent - Account Manager",
			"enabled": 1,
			"recipient_type": "Contract Field",
			"recipient_field": "account_manager",
			"trigger_mode": "On status change",
			"on_status": "Report sent",
			"channel": "Email",
			"show_popup": 1,
			"repeat_every_days": 0,
			"subject_template": tpl.REPORT_SENT_SUBJECT,
			"message_template": tpl.REPORT_SENT_MESSAGE,
		},
		{
			# Example of "Days after previous step": disabled by default, enable it in the UI.
			"step_no": 7,
			"step_label": "Helpdesk follow-up (not booked)",
			"enabled": 0,
			"recipient_type": "Role",
			"recipient_role": "HC Helpdesk",
			"trigger_mode": "Days after previous step if not resolved",
			"trigger_days": 3,
			"after_step_no": 1,
			"only_if_status_in": "Not started",
			"channel": "Email",
			"show_popup": 1,
			"repeat_every_days": 0,
			"subject_template": tpl.HELPDESK_FOLLOWUP_SUBJECT,
			"message_template": tpl.HELPDESK_FOLLOWUP_MESSAGE,
		},
	]


def create_default_flows(only_if_none_exist: bool = False):
	if only_if_none_exist and frappe.db.count("HC Notification Flow"):
		return

	for flow_name, frequency, is_default, days_from in FLOW_DEFINITIONS:
		if frappe.db.exists("HC Notification Flow", flow_name):
			continue
		first, second = FREQUENCY_DAYS[days_from]
		client_days = CLIENT_REMINDER_DAYS[days_from]
		flow = frappe.new_doc("HC Notification Flow")
		flow.update(
			{
				"flow_name": flow_name,
				"enabled": 1,
				"is_default": is_default,
				"applies_to_frequency": frequency,
				"description": (
					f"Helpdesk {first} days before due, Technical Manager {second} days before due "
					f"if still not started, daily overdue escalation, Account Manager on report sent. "
					f"Day values for {days_from} contracts."
				),
			}
		)
		for step in build_steps(first, second, client_days):
			flow.append("steps", step)
		flow.insert(ignore_permissions=True)


def upgrade_flow_to_v13(flow_name: str, days_from: str):
	"""Add the v1.3 steps / Arabic templates / ignore_pause to an existing default flow (idempotent)."""
	flow = frappe.get_doc("HC Notification Flow", flow_name)
	labels = {s.step_label for s in flow.steps}
	used = {int(s.step_no) for s in flow.steps}
	for step in v13_steps(CLIENT_REMINDER_DAYS[days_from]):
		if step["step_label"] in labels:
			continue
		while step["step_no"] in used:
			step["step_no"] += 1
		used.add(step["step_no"])
		flow.append("steps", add_arabic(step))
	for row in flow.steps:
		if row.step_label in ARABIC_TEMPLATES:
			row.subject_template_ar = row.subject_template_ar or ARABIC_TEMPLATES[row.step_label][0]
			row.message_template_ar = row.message_template_ar or ARABIC_TEMPLATES[row.step_label][1]
		if row.step_label == "Overdue escalation":
			row.ignore_pause = 1
	flow.flags.ignore_permissions = True
	flow.save()
