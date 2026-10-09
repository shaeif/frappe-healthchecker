# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.model.document import Document
from frappe.utils import cstr, getdate

from amc_tracker.cycle import cycle_label_of, get_cycle_visits, refresh_cycle_status
from amc_tracker.utils import (
	ROLE_ENGINEER,
	ROLE_HELPDESK,
	get_interval_months,
	is_active_engineer,
	is_full_access,
	split_list,
	user_roles,
)

# Fields a helpdesk user may change on an existing AMC (assigning engineers is their main job)
HELPDESK_FIELDS = {"engineers", "reminders_paused_until", "notes", "helpdesk_contact"}
# Fields an assigned engineer may change on an existing AMC
ENGINEER_FIELDS = {"combined_report", "findings_summary", "notes"}


class AMC(Document):
	def onload(self):
		from amc_tracker.notifications.engine import get_timeline_html

		try:
			self.set_onload("notification_timeline", get_timeline_html(self))
		except Exception:
			frappe.log_error(title=f"AMC Tracker: timeline failed for {self.name}")
			self.set_onload(
				"notification_timeline",
				'<p class="text-danger">{}</p>'.format(_("Could not build the timeline. See Error Log.")),
			)

	def validate(self):
		self.status = self.status or "Active"
		self.validate_restricted_changes()
		self.interval_months = get_interval_months(self.frequency)
		if not self.amc_title:
			self.amc_title = _("{0} AMC").format(self.client_name or self.client)
		if not self.account_manager and self.client:
			self.account_manager = frappe.db.get_value("Client", self.client, "account_manager")
		self.validate_dates()
		self.validate_engineers()
		self.set_notification_flow()
		self.cycle_label = cycle_label_of(self)
		self.validate_due_date_change()
		if not self.cycle_status:
			self.cycle_status = "Not started"

	def on_update(self):
		if self.has_value_changed("combined_report") and self.combined_report:
			self.mark_combined_visits()
		if not self.flags.signed_off_cycle and not self.is_new():
			refresh_cycle_status(self.name)

	# ------------------------------------------------------------------

	def validate_restricted_changes(self):
		"""Helpdesk assigns engineers; engineers attach the combined report. Everything else is for managers."""
		if self.is_new() or frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
			return
		if self.flags.signed_off_cycle or is_full_access():
			return
		roles = user_roles()
		if "AMC Account Manager" in roles:
			return
		allowed = set()
		if ROLE_HELPDESK in roles:
			allowed |= HELPDESK_FIELDS
		if ROLE_ENGINEER in roles:
			allowed |= ENGINEER_FIELDS
		before = self.get_doc_before_save()
		if not before:
			return
		changed = []
		for df in self.meta.fields:
			if df.fieldname in allowed or df.read_only:
				continue
			if df.fieldtype in table_fields:
				old = [(r.engineer, r.expertise, r.is_lead) for r in before.get(df.fieldname) or []] if df.fieldname == "engineers" else len(before.get(df.fieldname) or [])
				new = [(r.engineer, r.expertise, r.is_lead) for r in self.get(df.fieldname) or []] if df.fieldname == "engineers" else len(self.get(df.fieldname) or [])
				if old != new:
					changed.append(_(df.label))
				continue
			if df.fieldtype in no_value_fields:
				continue
			if cstr(self.get(df.fieldname)).strip() != cstr(before.get(df.fieldname)).strip():
				changed.append(_(df.label))
		if changed:
			frappe.throw(
				_("You cannot change: {0}. Ask a Technical Manager or Account Manager.").format(", ".join(changed)),
				frappe.PermissionError,
			)

	def validate_dates(self):
		if self.contract_start and self.contract_end and getdate(self.contract_end) < getdate(self.contract_start):
			frappe.throw(_("Contract End cannot be before Contract Start."))

	def validate_engineers(self):
		seen = set()
		for row in self.engineers:
			key = (row.engineer, row.expertise or "")
			if key in seen:
				frappe.throw(
					_("Row {0}: {1} is already listed for {2}.").format(row.idx, row.engineer_name or row.engineer, row.expertise or _("this AMC"))
				)
			seen.add(key)
			if row.engineer and (self.is_new() or row.engineer not in self._previous_engineers()) and not is_active_engineer(row.engineer):
				frappe.throw(_("Row {0}: {1} has no active Engineer profile.").format(row.idx, row.engineer_name or row.engineer))

	def _previous_engineers(self) -> set[str]:
		before = self.get_doc_before_save()
		return {r.engineer for r in (before.engineers if before else [])}

	def set_notification_flow(self):
		from amc_tracker.notifications.engine import get_flow_for_frequency

		if self.notification_flow and self.has_value_changed("frequency"):
			applies_to = frappe.db.get_value("AMC Notification Flow", self.notification_flow, "applies_to_frequency")
			if applies_to not in ("All", self.frequency):
				self.notification_flow = None
		if not self.notification_flow:
			self.notification_flow = get_flow_for_frequency(self.frequency)

	def validate_due_date_change(self):
		"""Moving the due date of a cycle that already has visits would orphan them."""
		if self.is_new() or self.flags.signed_off_cycle:
			return
		before = self.get_doc_before_save()
		if not before or not before.next_due_date:
			return
		old_label = cycle_label_of(before)
		if old_label != self.cycle_label and get_cycle_visits(self.name, old_label):
			frappe.throw(
				_("Cycle {0} already has PM visits. Sign it off (or cancel its visits) before moving the due date to another cycle.").format(old_label)
			)

	def mark_combined_visits(self):
		"""Visits ticked 'Included in the combined report' become Report submitted when it is attached."""
		for v in get_cycle_visits(self.name, cycle_label_of(self)):
			if v.included_in_combined and v.status != "Report submitted":
				visit = frappe.get_doc("PM Visit", v.name)
				visit.flags.skip_cycle_refresh = True
				visit.flags.ignore_permissions = True
				visit.save()


@frappe.whitelist()
def sign_off(amc: str):
	from amc_tracker.cycle import sign_off as _sign_off

	return _sign_off(amc)


def get_client_contacts(amc) -> dict:
	"""Primary contact + CC list of the AMC's client."""
	client = frappe.db.get_value(
		"Client", amc.client, ["contact_name", "contact_email", "contact_phone", "cc_emails", "preferred_contact_method"], as_dict=True
	) or frappe._dict()
	return frappe._dict(
		name=client.contact_name,
		email=client.contact_email,
		phone=client.contact_phone,
		cc=split_list(client.cc_emails),
		preferred=client.preferred_contact_method,
	)
