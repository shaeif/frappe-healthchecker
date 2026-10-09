# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint
from frappe.utils.jinja import validate_template

from amc_tracker.utils import AMC_USER_FIELDS, CYCLE_STATUSES, split_list

MODE_STATUS = "On cycle status change"
MODE_AFTER_PREVIOUS = "Days after previous step if not resolved"
# Recipient types that only make sense for rules about one PM visit
VISIT_ONLY_TARGETS = {"Visit Engineer"}
VISIT_MODES = {"On visit assigned", "Days before visit date", "On visit scheduled", "On visit rescheduled", "On visit report submitted"}


class AMCNotificationFlow(Document):
	def validate(self):
		if self.is_default and not self.enabled:
			frappe.throw(_("The default rule set must be enabled."))
		self.sort_steps()
		self.validate_steps()

	def on_update(self):
		if self.is_default:
			flow = frappe.qb.DocType("AMC Notification Flow")
			(
				frappe.qb.update(flow).set(flow.is_default, 0).where(flow.name != self.name).where(flow.is_default == 1)
			).run()

	def sort_steps(self):
		self.steps.sort(key=lambda s: (cint(s.step_no), s.idx))
		for idx, step in enumerate(self.steps, start=1):
			step.idx = idx

	def validate_steps(self):
		seen = set()
		step_numbers = {cint(s.step_no) for s in self.steps}
		for step in self.steps:
			label = _("Step {0} ({1})").format(step.step_no, step.step_label)
			if cint(step.step_no) <= 0:
				frappe.throw(_("Row {0}: Step No must be 1 or higher.").format(step.idx))
			if cint(step.step_no) in seen:
				frappe.throw(_("Step No {0} is used more than once.").format(step.step_no))
			seen.add(cint(step.step_no))

			if cint(step.trigger_days) < 0 or cint(step.repeat_every_days) < 0:
				frappe.throw(_("{0}: days cannot be negative.").format(label))
			if step.trigger_mode == MODE_STATUS and not step.on_status:
				frappe.throw(_("{0}: set On Cycle Status.").format(label))
			if step.trigger_mode == MODE_AFTER_PREVIOUS:
				after = cint(step.after_step_no)
				if after and (after not in step_numbers or after >= cint(step.step_no)):
					frappe.throw(_("{0}: After Step No must be an earlier step of this rule set.").format(label))
				if not after and not [n for n in step_numbers if n < cint(step.step_no)]:
					frappe.throw(_("{0}: there is no previous step to wait for.").format(label))

			for prefix in ("recipient", "cc"):
				self.validate_target(step, prefix, label)

			for fieldname in ("only_if_status_in", "stop_when_status"):
				unknown = [s for s in split_list(step.get(fieldname)) if s not in CYCLE_STATUSES]
				if unknown:
					frappe.throw(
						_("{0}: unknown cycle status {1} in {2}. Use: {3}").format(
							label, ", ".join(unknown), _(step.meta.get_label(fieldname)), ", ".join(CYCLE_STATUSES)
						)
					)

			for fieldname in ("subject_template", "message_template", "subject_template_ar", "message_template_ar"):
				if step.get(fieldname):
					validate_template(step.get(fieldname))

	def validate_target(self, step, prefix, label):
		kind = step.get(f"{prefix}_type")
		if not kind:
			return
		who = _("recipient") if prefix == "recipient" else _("CC")
		if kind in VISIT_ONLY_TARGETS and step.trigger_mode not in VISIT_MODES:
			frappe.throw(_("{0}: '{1}' can only be used with a visit trigger (e.g. Days before visit date).").format(label, _(kind)))
		if kind == "AMC Field" and step.get(f"{prefix}_field") not in AMC_USER_FIELDS:
			frappe.throw(_("{0}: choose an AMC field for the {1}.").format(label, who))
		if kind == "Role" and not step.get(f"{prefix}_role"):
			frappe.throw(_("{0}: choose a role for the {1}.").format(label, who))
		if kind == "Specific User" and not step.get(f"{prefix}_user"):
			frappe.throw(_("{0}: choose a user for the {1}.").format(label, who))
		if kind == "Email Address":
			addresses = split_list(step.get(f"{prefix}_email"))
			if not addresses:
				frappe.throw(_("{0}: enter an email address for the {1}.").format(label, who))
			for address in addresses:
				frappe.utils.validate_email_address(address, throw=True)
