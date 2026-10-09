# Copyright (c) 2026, HC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.model.document import Document
from frappe.utils import add_months, cstr, date_diff, getdate, now_datetime, today

from hc_tracker.utils import (
	ROLE_ACCOUNT_MANAGER,
	ROLE_ENGINEER,
	ROLE_HELPDESK,
	can_sign_off,
	get_interval_months,
	get_period_label,
	is_full_access,
	user_roles,
)

OPEN_WORK_STATUSES = ("Not started", "Scheduled", "In progress")
# Fields a Helpdesk-only user may change on an existing contract
HELPDESK_EDITABLE_FIELDS = {
	"status",
	"scheduled_date",
	"reschedule_reason",
	"reschedule_note",
	"reminders_paused_until",
	"client_contact_name",
	"client_contact_email",
	"client_contact_phone",
	"client_cc_emails",
	"preferred_contact_method",
}


class HCContract(Document):
	def onload(self):
		from hc_tracker.notifications.engine import get_timeline_html

		try:
			self.set_onload("notification_timeline", get_timeline_html(self))
		except Exception:
			frappe.log_error(title=f"HC Tracker: timeline failed for {self.name}")
			self.set_onload(
				"notification_timeline",
				'<p class="text-danger">{}</p>'.format(_("Could not build the timeline. See Error Log.")),
			)

	def before_validate(self):
		if self.client_id:
			self.client_id = self.client_id.strip()

	def validate(self):
		self.validate_helpdesk_changes()
		self.interval_months = get_interval_months(self.frequency)
		self.validate_dates()
		self.validate_client_contact()
		self.set_notification_flow()
		self.set_report_sent()
		self.validate_scheduled()
		self.check_engineer_availability()
		self.track_reschedule()
		self.process_sign_off()
		self.capture_status_event()

	def on_update(self):
		events = self.flags.get("hc_status_events") or []
		self.flags.hc_status_events = []
		reschedule = self.flags.get("hc_reschedule")
		self.flags.hc_reschedule = None
		if frappe.flags.in_import or frappe.flags.in_install or frappe.flags.in_migrate:
			return

		from hc_tracker.notifications.engine import fire_reschedule, fire_status_change

		if reschedule:
			try:
				fire_reschedule(self, **reschedule)
			except Exception:
				frappe.log_error(title=f"HC Tracker: reschedule notification failed for {self.name}")

		for status, cycle_label in events:
			try:
				fire_status_change(self, status, cycle_label)
			except Exception:
				frappe.log_error(title=f"HC Tracker: status notification failed for {self.name}")

	# ------------------------------------------------------------------
	# Validation helpers
	# ------------------------------------------------------------------

	def validate_helpdesk_changes(self):
		"""Helpdesk-only users may only book: status Not started -> Scheduled and scheduled_date."""
		if self.is_new() or frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
			return
		user = frappe.session.user
		if is_full_access(user):
			return
		before = self.get_doc_before_save()
		if not before:
			return
		roles = user_roles(user)
		if ROLE_ACCOUNT_MANAGER in roles and before.account_manager == user:
			return
		if ROLE_ENGINEER in roles and before.assigned_engineer == user:
			return
		if ROLE_HELPDESK not in roles:
			return

		changed = []
		for df in self.meta.fields:
			if df.fieldtype in table_fields:
				if len(self.get(df.fieldname) or []) != len(before.get(df.fieldname) or []):
					changed.append(_(df.label))
				continue
			if df.fieldtype in no_value_fields or df.fieldname in HELPDESK_EDITABLE_FIELDS or df.read_only:
				continue
			if cstr(self.get(df.fieldname)).strip() != cstr(before.get(df.fieldname)).strip():
				changed.append(_(df.label))
		if changed:
			frappe.throw(
				_("Helpdesk can only change the booking, the client contact and the reminder pause. Not allowed: {0}").format(
					", ".join(changed)
				),
				frappe.PermissionError,
			)

		if self.status != before.status and not (before.status == "Not started" and self.status == "Scheduled"):
			frappe.throw(
				_("Helpdesk can only change the status from Not started to Scheduled."),
				frappe.PermissionError,
			)

	def validate_dates(self):
		if self.contract_start and self.contract_end and getdate(self.contract_end) < getdate(self.contract_start):
			frappe.throw(_("Contract End cannot be before Contract Start."))

	def validate_client_contact(self):
		from hc_tracker.utils import split_list

		if self.client_contact_email:
			frappe.utils.validate_email_address(self.client_contact_email.strip(), throw=True)
		for address in split_list(self.client_cc_emails):
			frappe.utils.validate_email_address(address, throw=True)

	def check_engineer_availability(self):
		"""Warn (or block, per HC Settings) when the booking clashes with leave, another booking or a holiday."""
		if not self.scheduled_date or self.status not in ("Scheduled", "In progress"):
			return
		if not (self.is_new() or self.has_value_changed("scheduled_date") or self.has_value_changed("assigned_engineer")
				or self.has_value_changed("status")):
			return
		from hc_tracker.scheduling import check_availability
		from hc_tracker.utils import get_settings

		problems = check_availability(self.assigned_engineer, self.scheduled_date, None if self.is_new() else self.name)
		if not problems:
			return
		message = "<br>".join(p["message"] for p in problems)
		if frappe.utils.cint(get_settings().block_unavailable_booking):
			frappe.throw(message, title=_("Engineer not available"))
		frappe.msgprint(message, title=_("Check the booking"), indicator="orange")

	def track_reschedule(self):
		"""Record a changed booked date in the Reschedule History and trigger 'On reschedule' steps."""
		self.flags.hc_reschedule = None
		before = self.get_doc_before_save()
		if self.is_new() or not before or not before.scheduled_date or not self.scheduled_date:
			if not self.scheduled_date:
				self.reschedule_reason = None
				self.reschedule_note = None
			return
		if getdate(before.scheduled_date) == getdate(self.scheduled_date):
			return
		reason = self.reschedule_reason or _("Not specified")
		self.append(
			"reschedules",
			{
				"changed_on": now_datetime(),
				"old_date": before.scheduled_date,
				"new_date": self.scheduled_date,
				"reason": reason,
				"note": self.reschedule_note,
				"changed_by": frappe.session.user,
			},
		)
		self.last_rescheduled_on = now_datetime()
		self.flags.hc_reschedule = {
			"old_date": before.scheduled_date,
			"reason": reason,
			"note": self.reschedule_note,
		}
		self.reschedule_reason = None
		self.reschedule_note = None

	def set_notification_flow(self):
		from hc_tracker.notifications.engine import get_flow_for_frequency

		if self.notification_flow and self.has_value_changed("frequency"):
			applies_to = frappe.db.get_value("HC Notification Flow", self.notification_flow, "applies_to_frequency")
			if applies_to not in ("All", self.frequency):
				self.notification_flow = None
		if not self.notification_flow:
			self.notification_flow = get_flow_for_frequency(self.frequency)

	def set_report_sent(self):
		if self.current_report and self.status in OPEN_WORK_STATUSES and self.has_value_changed("current_report"):
			self.status = "Report sent"
			frappe.msgprint(_("Report attached: status set to Report sent."), alert=True, indicator="green")

	def validate_scheduled(self):
		if self.status == "Scheduled" and not self.scheduled_date:
			frappe.throw(_("Set the Scheduled Date (booked HC window) before setting the status to Scheduled."))

	def process_sign_off(self):
		"""Close the cycle: history row, last HC date, roll the due date, reset the current cycle."""
		self.flags.hc_signed_off_cycle = None
		if self.status != "Signed off":
			return
		if not can_sign_off():
			frappe.throw(
				_("Only an HC Account Manager or HC Technical Manager can set the status to Signed off."),
				frappe.PermissionError,
			)
		if not self.current_report:
			frappe.throw(_("Attach the HC report (Current Report) before signing off."))

		previous_due = getdate(self.next_due_date)
		cycle_label = get_period_label(previous_due, self.frequency)
		hc_date = getdate(self.scheduled_date) if self.scheduled_date else getdate(today())

		self.append(
			"cycles",
			{
				"hc_date": hc_date,
				"period_label": cycle_label,
				"due_date": previous_due,
				"signed_off_on": getdate(today()),
				"days_late": date_diff(hc_date, previous_due),
				"engineer": self.assigned_engineer,
				"report": self.current_report,
				"sign_off_file": self.current_signoff,
				"findings_summary": self.findings_summary,
				"signed_off_by": frappe.session.user,
			},
		)
		self.last_hc_date = hc_date
		# Roll forward from the PREVIOUS DUE DATE, not from the sign-off date
		self.next_due_date = add_months(previous_due, self.interval_months or get_interval_months(self.frequency))
		self.current_report = None
		self.current_signoff = None
		self.findings_summary = None
		self.scheduled_date = None
		self.status = "Not started"
		self.flags.hc_signed_off_cycle = cycle_label

		frappe.msgprint(
			_("Cycle {0} signed off. Next due date: {1}. A new notification cycle has started.").format(
				cycle_label, frappe.utils.formatdate(self.next_due_date)
			),
			alert=True,
			indicator="green",
		)

	def capture_status_event(self):
		"""Remember which status change happened so on_update can fire 'On status change' steps."""
		events = []
		if self.flags.hc_signed_off_cycle:
			events.append(("Signed off", self.flags.hc_signed_off_cycle))
		else:
			before = self.get_doc_before_save()
			old_status = before.status if before else None
			if self.status != old_status and self.status != "Not started":
				events.append((self.status, get_period_label(self.next_due_date, self.frequency)))
		self.flags.hc_status_events = events
