# Copyright (c) 2026, AMC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from amc_tracker.utils import ROLE_ENGINEER


class Engineer(Document):
	def validate(self):
		self.status = self.status or "Active"
		if self.user in ("Guest", "Administrator"):
			frappe.throw(_("{0} cannot be an engineer.").format(self.user))
		seen = set()
		for row in self.expertise:
			if row.expertise in seen:
				frappe.throw(_("{0} is listed twice.").format(row.expertise))
			seen.add(row.expertise)

	def on_update(self):
		# Any user (helpdesk, manager...) can also be an engineer: give them the role when they get a profile.
		# An inactive profile does not, so taking someone out of the Engineer group sticks.
		if self.status == "Active" and ROLE_ENGINEER not in frappe.get_roles(self.user):
			user = frappe.get_doc("User", self.user)
			user.flags.ignore_permissions = True
			user.add_roles(ROLE_ENGINEER)


def get_expertise(engineer: str) -> list[str]:
	return frappe.get_all(
		"Engineer Expertise", filters={"parenttype": "Engineer", "parent": engineer}, pluck="expertise", order_by="idx"
	)


@frappe.whitelist()
def expertise_of(engineer: str) -> list[str]:
	"""Areas of expertise of one engineer (used to fill the AMC Engineers table and the assign dialog)."""
	return get_expertise(engineer)
