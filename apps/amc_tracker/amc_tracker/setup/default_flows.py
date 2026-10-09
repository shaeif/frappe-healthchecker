"""Default "Standard PM Notifications" rule sets.

One default rule set (applies to All, Quarterly day values) plus one copy per PM frequency whose day
values match that frequency. AMCs automatically use the rule set matching their frequency. Everything
here is editable afterwards in Settings > Notification Rules.
"""

import frappe

from amc_tracker.notifications import templates as tpl

# frequency: (days before due -> helpdesk "assign engineers", days before due -> Technical Manager escalation)
FREQUENCY_DAYS = {
	"Monthly": (10, 3),
	"Quarterly": (30, 7),
	"Half-yearly": (45, 14),
	"Yearly": (60, 30),
}
# days before due when engineers who still have no visit date get a reminder (repeats every 3 days)
SCHEDULE_REMINDER_DAYS = {"Monthly": 7, "Quarterly": 21, "Half-yearly": 30, "Yearly": 45}
# days before the visit date: (engineer preparation, client reminder)
VISIT_DAYS = {"Monthly": (1, 1), "Quarterly": (2, 2), "Half-yearly": (3, 2), "Yearly": (3, 2)}

DEFAULT_FLOW_NAME = "Standard PM Notifications"

FLOW_DEFINITIONS = [
	# (name, applies_to_frequency, is_default, day values taken from)
	(DEFAULT_FLOW_NAME, "All", 1, "Quarterly"),
	(f"{DEFAULT_FLOW_NAME} - Monthly", "Monthly", 0, "Monthly"),
	(f"{DEFAULT_FLOW_NAME} - Quarterly", "Quarterly", 0, "Quarterly"),
	(f"{DEFAULT_FLOW_NAME} - Half-yearly", "Half-yearly", 0, "Half-yearly"),
	(f"{DEFAULT_FLOW_NAME} - Yearly", "Yearly", 0, "Yearly"),
]

HELPDESK = "AMC Helpdesk"
TECH_MANAGER = "AMC Technical Manager"


def _step(no, label, templates, **kw):
	subject, message, subject_ar, message_ar = templates
	step = {
		"step_no": no,
		"step_label": label,
		"enabled": 1,
		"channel": "Email",
		"show_popup": 1,
		"repeat_every_days": 0,
		"subject_template": subject,
		"message_template": message,
		"subject_template_ar": subject_ar,
		"message_template_ar": message_ar,
	}
	step.update(kw)
	return step


def T(name):
	return (getattr(tpl, f"{name}_SUBJECT"), getattr(tpl, f"{name}_MESSAGE"), getattr(tpl, f"{name}_SUBJECT_AR"), getattr(tpl, f"{name}_MESSAGE_AR"))


def build_steps(frequency: str) -> list[dict]:
	assign_days, escalate_days = FREQUENCY_DAYS[frequency]
	prep_days, client_days = VISIT_DAYS[frequency]
	return [
		_step(
			1, "Helpdesk - assign engineers", T("ASSIGN"),
			recipient_type="Role", recipient_role=HELPDESK,
			trigger_mode="Days before due date", trigger_days=assign_days,
			only_if_status_in="Not started",
		),
		_step(
			2, "Engineer - assigned, please schedule your visit", T("PLEASE_SCHEDULE"),
			recipient_type="Visit Engineer",
			trigger_mode="On visit assigned",
		),
		_step(
			3, "Engineers - visit date still not set", T("SCHEDULE_REMINDER"),
			recipient_type="Engineers Yet To Schedule", cc_type="Role", cc_role=HELPDESK,
			trigger_mode="Days before due date", trigger_days=SCHEDULE_REMINDER_DAYS[frequency],
			only_if_status_in="Engineers assigned", repeat_every_days=3,
		),
		_step(
			4, "Helpdesk - visit scheduled", T("VISIT_SCHEDULED"),
			recipient_type="Role", recipient_role=HELPDESK,
			trigger_mode="On visit scheduled", channel="System Notification",
		),
		_step(
			5, "Engineer - visit preparation", T("VISIT_PREP"),
			recipient_type="Visit Engineer",
			trigger_mode="Days before visit date", trigger_days=prep_days,
		),
		_step(
			6, "Client - visit reminder", T("CLIENT_REMINDER"),
			recipient_type="Client Contact", cc_type="Visit Engineer",
			trigger_mode="Days before visit date", trigger_days=client_days, show_popup=0,
		),
		_step(
			7, "Technical Manager - PM not scheduled", T("TM"),
			recipient_type="AMC Field", recipient_field="technical_manager", fallback_role=TECH_MANAGER,
			trigger_mode="Days before due date", trigger_days=escalate_days,
			only_if_status_in="Not started,Engineers assigned", channel="Email + Teams",
		),
		_step(
			8, "Overdue escalation", T("OVERDUE"),
			recipient_type="AMC Field", recipient_field="technical_manager", fallback_role=TECH_MANAGER,
			cc_type="AMC Field", cc_field="account_manager",
			trigger_mode="Days after due date (overdue)", trigger_days=1, repeat_every_days=1,
			stop_when_status="Signed off", ignore_pause=1, channel="Email + Teams",
		),
		_step(
			9, "Visit rescheduled", T("RESCHEDULED"),
			recipient_type="Visit Engineer", cc_type="Role", cc_role=HELPDESK,
			trigger_mode="On visit rescheduled",
		),
		_step(
			10, "Account Manager - reports ready for sign-off", T("REPORTS_READY"),
			recipient_type="AMC Field", recipient_field="account_manager", fallback_role=TECH_MANAGER,
			trigger_mode="On cycle status change", on_status="Reports submitted",
		),
		_step(
			# Optional: confirmation email to the client when a visit date is set. Disabled by default.
			11, "Client - visit confirmation", T("CLIENT_CONFIRMATION"),
			enabled=0, recipient_type="Client Contact", cc_type="Visit Engineer",
			trigger_mode="On visit scheduled", show_popup=0,
		),
	]


def create_default_flows(only_if_none_exist: bool = False):
	if only_if_none_exist and frappe.db.count("AMC Notification Flow"):
		return
	for flow_name, frequency, is_default, days_from in FLOW_DEFINITIONS:
		if frappe.db.exists("AMC Notification Flow", flow_name):
			continue
		assign_days, escalate_days = FREQUENCY_DAYS[days_from]
		flow = frappe.new_doc("AMC Notification Flow")
		flow.update(
			{
				"flow_name": flow_name,
				"enabled": 1,
				"is_default": is_default,
				"applies_to_frequency": frequency,
				"description": (
					f"Helpdesk assigns engineers {assign_days} days before the PM due date; engineers schedule their "
					f"visits; Technical Manager escalation {escalate_days} days before due if not scheduled; daily "
					f"overdue escalation; Account Manager when all reports are in. Day values for {days_from} AMCs."
				),
			}
		)
		for step in build_steps(days_from):
			flow.append("steps", step)
		flow.insert(ignore_permissions=True)
