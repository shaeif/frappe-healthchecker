# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.model.document import Document
from frappe.utils import cint, cstr, getdate, now_datetime, today

from amc_tracker.cycle import cycle_label_of, refresh_cycle_status, visit_status
from amc_tracker.utils import (
	ROLE_ENGINEER,
	VISIT_CANCELLED,
	VISIT_REPORTED,
	VISIT_SCHEDULED,
	get_settings,
	sees_all,
	user_roles,
)

# What the visit's own engineer may change (the rest is set by the helpdesk)
ENGINEER_FIELDS = {
	"visit_date", "visit_mode", "start_time", "end_time", "reschedule_reason", "reschedule_note",
	"expertise_covered", "visit_notes", "report", "included_in_combined", "completed_on", "findings",
}


class PMVisit(Document):
	def validate(self):
		amc = frappe.get_doc("AMC", self.amc) if self.amc else None
		if self.is_new() and amc:
			self.cycle_label = self.cycle_label or cycle_label_of(amc)
			self.due_date = self.due_date or amc.next_due_date
		self.visit_mode = self.visit_mode or "On-site"
		self.validate_engineer_changes()
		self.validate_times()
		if self.report and not self.completed_on:
			self.completed_on = self.visit_date if self.visit_date and getdate(self.visit_date) <= getdate(today()) else getdate(today())
		self.status = visit_status(self, amc.combined_report if amc else None)
		self.check_availability()
		self.track_reschedule()
		self.capture_events()

	def after_insert(self):
		"""A visit added by hand for an engineer who is not on the AMC yet adds them to its Engineers table."""
		if self.flags.engineer_on_team:
			return
		amc = frappe.get_doc("AMC", self.amc)
		if any(r.engineer == self.engineer for r in amc.engineers):
			return
		expertise = self.expertise_covered[0].expertise if self.expertise_covered else None
		amc.append("engineers", {"engineer": self.engineer, "expertise": expertise})
		amc.flags.ignore_permissions = True
		amc.save()

	def on_update(self):
		events = self.flags.get("visit_events") or []
		self.flags.visit_events = []
		if not self.flags.skip_cycle_refresh:
			refresh_cycle_status(self.amc)
		if frappe.flags.in_import or frappe.flags.in_install or frappe.flags.in_migrate:
			return
		from amc_tracker.notifications.engine import fire_visit_event

		for mode, extra in events:
			try:
				fire_visit_event(self, mode, extra)
			except Exception:
				frappe.log_error(title=f"AMC Tracker: visit notification failed for {self.name}")

	def on_trash(self):
		self.flags.amc_to_refresh = self.amc

	def after_delete(self):
		if self.flags.get("amc_to_refresh") and frappe.db.exists("AMC", self.amc):
			refresh_cycle_status(self.amc, fire=False)

	# ------------------------------------------------------------------

	def validate_engineer_changes(self):
		"""An engineer (without helpdesk/manager rights) may only plan and report their own visit."""
		if self.is_new() or sees_all() or frappe.flags.in_install or frappe.flags.in_patch:
			return
		if ROLE_ENGINEER not in user_roles():
			return
		before = self.get_doc_before_save()
		if not before:
			return
		changed = []
		for df in self.meta.fields:
			if df.fieldname in ENGINEER_FIELDS or df.read_only or df.fieldtype in no_value_fields:
				continue
			if df.fieldtype in table_fields:
				continue
			if cstr(self.get(df.fieldname)).strip() != cstr(before.get(df.fieldname)).strip():
				changed.append(_(df.label))
		if changed:
			frappe.throw(_("Engineers can only plan and report their visit. Not allowed: {0}").format(", ".join(changed)), frappe.PermissionError)

	def validate_times(self):
		if self.start_time and self.end_time and cstr(self.end_time) <= cstr(self.start_time):
			frappe.throw(_("'To' time must be after 'From' time."))

	def check_availability(self):
		"""Warn (or block, per AMC Settings) when the date is a holiday/weekend, the engineer is on leave or busy."""
		if not self.visit_date or self.status == VISIT_CANCELLED:
			return
		if not (self.is_new() or self.has_value_changed("visit_date") or self.has_value_changed("engineer")):
			return
		from amc_tracker.scheduling import check_availability

		problems = check_availability(self.engineer, self.visit_date, None if self.is_new() else self.name)
		if not problems:
			return
		message = "<br>".join(p["message"] for p in problems)
		if cint(get_settings().block_unavailable_booking):
			frappe.throw(message, title=_("Engineer not available"))
		frappe.msgprint(message, title=_("Check the visit date"), indicator="orange")

	def track_reschedule(self):
		before = None if self.is_new() else self.get_doc_before_save()
		self.flags.rescheduled = None
		if not before or not before.visit_date or not self.visit_date or getdate(before.visit_date) == getdate(self.visit_date):
			if not self.visit_date:
				self.reschedule_reason = None
				self.reschedule_note = None
			return
		reason = self.reschedule_reason or _("Not specified")
		self.append(
			"reschedules",
			{
				"changed_on": now_datetime(),
				"old_date": before.visit_date,
				"new_date": self.visit_date,
				"reason": reason,
				"note": self.reschedule_note,
				"changed_by": frappe.session.user,
			},
		)
		self.last_rescheduled_on = now_datetime()
		self.flags.rescheduled = {"old_date": before.visit_date, "reason": reason, "note": self.reschedule_note}
		self.reschedule_reason = None
		self.reschedule_note = None

	def capture_events(self):
		from amc_tracker.notifications.engine import (
			MODE_VISIT_ASSIGNED,
			MODE_VISIT_REPORTED,
			MODE_VISIT_RESCHEDULED,
			MODE_VISIT_SCHEDULED,
		)

		events = []
		if self.is_new() and self.status != VISIT_CANCELLED:
			events.append((MODE_VISIT_ASSIGNED, None))
		before = None if self.is_new() else self.get_doc_before_save()
		had_date = bool(before and before.visit_date)
		if self.visit_date and not had_date and self.status != VISIT_CANCELLED:
			events.append((MODE_VISIT_SCHEDULED, None))
		if self.flags.rescheduled and self.status != VISIT_CANCELLED:
			events.append((MODE_VISIT_RESCHEDULED, self.flags.rescheduled))
		if self.status == VISIT_REPORTED and (not before or before.status != VISIT_REPORTED):
			events.append((MODE_VISIT_REPORTED, None))
		self.flags.visit_events = events


@frappe.whitelist()
def cancel_visit(name: str, reason: str | None = None):
	doc = frappe.get_doc("PM Visit", name)
	if not sees_all():
		frappe.throw(_("Only the helpdesk or a manager can cancel a visit."), frappe.PermissionError)
	doc.check_permission("write")
	doc.status = VISIT_CANCELLED
	if reason:
		doc.visit_notes = "\n".join(x for x in (doc.visit_notes, _("Cancelled: {0}").format(reason)) if x)
	doc.save()
	return doc.status


@frappe.whitelist()
def mark_completed(name: str, completed_on: str | None = None):
	doc = frappe.get_doc("PM Visit", name)
	doc.check_permission("write")
	if not doc.visit_date:
		frappe.throw(_("Set the visit date first."))
	doc.completed_on = getdate(completed_on) if completed_on else getdate(today())
	doc.save()
	return doc.status


@frappe.whitelist()
def reopen_visit(name: str):
	doc = frappe.get_doc("PM Visit", name)
	if not sees_all():
		frappe.throw(_("Only the helpdesk or a manager can reopen a visit."), frappe.PermissionError)
	doc.check_permission("write")
	doc.status = VISIT_SCHEDULED if doc.visit_date else "To be scheduled"
	doc.save()
	return doc.status
